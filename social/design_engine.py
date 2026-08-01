"""
Social Design Engine - Antes do Sino
========================================

Modulo TOTALMENTE ISOLADO - nao importa nada de main.py nem de
social_content_engine.py (cada modulo e independente, testavel
sozinho). Le o conteudo JA GERADO e JA APROVADO em
docs/social_queue.json e transforma em ativos visuais, usando so
Python + Pillow. Sem IA de imagem, sem API paga, sem custo externo.

Responsabilidade unica: conteudo aprovado -> ativo visual. NAO decide
assunto, NAO gera texto, NAO decide aprovacao - so processa itens com
status == "approved".

O tipo de ativo visual NUNCA e assumido a partir do content_mode. Cada
item ja chega com um campo "content_template" (definido pelo content
engine). Este modulo mantem sua PROPRIA tabela local
(template -> tipo de ativo), evitando qualquer acoplamento entre os
dois modulos isolados:

    content_template   ->   tipo de ativo
    "deep_dive"        ->   carousel (5-7 slides)
    "quick_insight"    ->   card (imagem unica)
    "market_snapshot"  ->   card (imagem unica)

X nunca gera ativo visual (e so texto). TikTok gera um roteiro
estruturado em texto (nao video, nesta fase).

Fluxo:
    docs/social_queue.json (item com status == "approved")
        -> gerar_ativo_visual()  [Instagram: carousel ou card]
        -> formatar_roteiro_tiktok()  [TikTok: arquivo de roteiro]
        -> docs/social_posts/{data}_{slug}/...
        -> notificacao privada confirmando "pronto para publicacao"
        -> status = "designed"
"""

import os
import re
import json
import unicodedata
from datetime import datetime, timedelta, timezone

import requests
from PIL import Image, ImageDraw, ImageFont

BR_TZ = timezone(timedelta(hours=-3))

SOCIAL_QUEUE_FILE = "docs/social_queue.json"
SOCIAL_POSTS_DIR = "docs/social_posts"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")

# Tabela LOCAL - o design engine so entende "template", nunca "modo".
# Se um novo modo for criado no content engine com um template ja
# existente aqui, o design funciona sem nenhuma alteracao neste arquivo.
DESIGN_MAP = {
    "deep_dive": "carousel",
    "quick_insight": "card",
    "market_snapshot": "card",
}

# ---------------------------------------------------------------------------
# Identidade visual - terminal/mesa de operacoes, fundo escuro, azul/cinza
# ---------------------------------------------------------------------------

TAMANHO_CANVAS = 1080

COR_FUNDO = (9, 13, 22)
COR_AZUL = (59, 130, 246)
COR_CINZA = (100, 116, 139)
COR_CINZA_CLARO = (148, 163, 184)
COR_BRANCO = (245, 245, 247)

MARGEM = 90

CAMINHOS_FONTE_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
CAMINHOS_FONTE_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def carregar_fonte(tamanho, negrito=True):
    caminhos = CAMINHOS_FONTE_BOLD if negrito else CAMINHOS_FONTE_REGULAR
    for caminho in caminhos:
        try:
            if os.path.exists(caminho):
                return ImageFont.truetype(caminho, tamanho)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=tamanho)
    except Exception:
        return ImageFont.load_default()


def slugify_local(texto):
    texto = texto or "tema"
    normalizado = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    minusculo = sem_acento.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", minusculo).strip("-")
    return slug[:60] if slug else "tema"


# ---------------------------------------------------------------------------
# Quebra de texto e desenho
# ---------------------------------------------------------------------------

def quebrar_texto(draw, texto, fonte, largura_maxima):
    palavras = (texto or "").split()
    if not palavras:
        return []
    linhas = []
    linha_atual = ""
    for palavra in palavras:
        candidata = (linha_atual + " " + palavra).strip()
        bbox = draw.textbbox((0, 0), candidata, font=fonte)
        largura_candidata = bbox[2] - bbox[0]
        if largura_candidata <= largura_maxima or not linha_atual:
            linha_atual = candidata
        else:
            linhas.append(linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(linha_atual)
    return linhas


def desenhar_linhas(draw, linhas, fonte, y_inicio, cor, espacamento_linha, alinhamento="left", largura_canvas=TAMANHO_CANVAS):
    y = y_inicio
    for linha in linhas:
        bbox = draw.textbbox((0, 0), linha, font=fonte)
        largura_linha = bbox[2] - bbox[0]
        altura_linha = bbox[3] - bbox[1]
        x = (largura_canvas - largura_linha) / 2 if alinhamento == "center" else MARGEM
        draw.text((x, y), linha, font=fonte, fill=cor)
        y += altura_linha + espacamento_linha
    return y


def _base_slide():
    img = Image.new("RGB", (TAMANHO_CANVAS, TAMANHO_CANVAS), COR_FUNDO)
    draw = ImageDraw.Draw(img)
    return img, draw


def _desenhar_rodape(draw, numero_slide, total_slides):
    fonte_rodape = carregar_fonte(22, negrito=False)
    draw.text((MARGEM, TAMANHO_CANVAS - 70), "ANTES DO SINO", font=fonte_rodape, fill=COR_CINZA)
    if total_slides > 1:
        texto_numero = str(numero_slide).zfill(2) + "/" + str(total_slides).zfill(2)
        bbox = draw.textbbox((0, 0), texto_numero, font=fonte_rodape)
        largura = bbox[2] - bbox[0]
        draw.text((TAMANHO_CANVAS - MARGEM - largura, TAMANHO_CANVAS - 70), texto_numero, font=fonte_rodape, fill=COR_CINZA)
    draw.line([(MARGEM, TAMANHO_CANVAS - 100), (TAMANHO_CANVAS - MARGEM, TAMANHO_CANVAS - 100)], fill=COR_CINZA, width=2)


def _desenhar_corpo_com_autoajuste(draw, texto, y_inicio, espaco_disponivel):
    for tamanho_fonte in [38, 34, 30, 27, 24, 22]:
        fonte_corpo = carregar_fonte(tamanho_fonte, negrito=False)
        linhas_corpo = quebrar_texto(draw, texto, fonte_corpo, TAMANHO_CANVAS - 2 * MARGEM)
        espacamento = 16 if tamanho_fonte >= 30 else 10
        altura_estimada = len(linhas_corpo) * (tamanho_fonte + espacamento + 8)
        if altura_estimada <= espaco_disponivel or tamanho_fonte == 22:
            desenhar_linhas(draw, linhas_corpo, fonte_corpo, y_inicio, COR_BRANCO, espacamento_linha=espacamento)
            return


# ---------------------------------------------------------------------------
# CAROUSEL (template "deep_dive") - 6 slides a partir dos campos
# semanticos do instagram (hook/context/why_it_matters/impact/
# watch_next/cta) - nao depende mais de slide_1..slide_6 fixos.
# ---------------------------------------------------------------------------

def criar_slide_capa(headline, hook):
    img, draw = _base_slide()
    fonte_marca = carregar_fonte(30, negrito=True)
    fonte_titulo = carregar_fonte(60, negrito=True)
    fonte_hook = carregar_fonte(34, negrito=False)

    draw.text((MARGEM, MARGEM), "ANTES DO SINO", font=fonte_marca, fill=COR_AZUL)
    draw.line([(MARGEM, MARGEM + 55), (MARGEM + 90, MARGEM + 55)], fill=COR_AZUL, width=4)

    linhas_titulo = quebrar_texto(draw, headline, fonte_titulo, TAMANHO_CANVAS - 2 * MARGEM)
    y = 340
    y = desenhar_linhas(draw, linhas_titulo, fonte_titulo, y, COR_BRANCO, espacamento_linha=14)

    y += 40
    linhas_hook = quebrar_texto(draw, hook, fonte_hook, TAMANHO_CANVAS - 2 * MARGEM)
    desenhar_linhas(draw, linhas_hook, fonte_hook, y, COR_CINZA_CLARO, espacamento_linha=10)

    _desenhar_rodape(draw, 1, 6)
    return img


def criar_slide_conteudo(numero_slide, cabecalho, corpo, total_slides):
    img, draw = _base_slide()
    fonte_kicker = carregar_fonte(24, negrito=True)
    fonte_cabecalho = carregar_fonte(46, negrito=True)

    draw.text((MARGEM, MARGEM), "ANTES DO SINO", font=fonte_kicker, fill=COR_AZUL)

    y_titulo = MARGEM + 70
    linhas_cabecalho = quebrar_texto(draw, cabecalho, fonte_cabecalho, TAMANHO_CANVAS - 2 * MARGEM)
    y_apos_titulo = desenhar_linhas(draw, linhas_cabecalho, fonte_cabecalho, y_titulo, COR_AZUL, espacamento_linha=8)

    draw.line([(MARGEM, y_apos_titulo + 20), (TAMANHO_CANVAS - MARGEM, y_apos_titulo + 20)], fill=COR_CINZA, width=2)
    y_corpo_inicio = y_apos_titulo + 60
    espaco_disponivel = (TAMANHO_CANVAS - 130) - y_corpo_inicio

    _desenhar_corpo_com_autoajuste(draw, corpo, y_corpo_inicio, espaco_disponivel)

    _desenhar_rodape(draw, numero_slide, total_slides)
    return img


def criar_slide_encerramento(texto_final, total_slides):
    img, draw = _base_slide()
    fonte_marca = carregar_fonte(52, negrito=True)
    fonte_texto = carregar_fonte(34, negrito=False)

    texto_marca = "ANTES DO SINO"
    bbox = draw.textbbox((0, 0), texto_marca, font=fonte_marca)
    largura_marca = bbox[2] - bbox[0]
    draw.text(((TAMANHO_CANVAS - largura_marca) / 2, 420), texto_marca, font=fonte_marca, fill=COR_BRANCO)

    draw.line([(TAMANHO_CANVAS / 2 - 60, 500), (TAMANHO_CANVAS / 2 + 60, 500)], fill=COR_AZUL, width=4)

    linhas = quebrar_texto(draw, texto_final, fonte_texto, TAMANHO_CANVAS - 2 * MARGEM)
    desenhar_linhas(draw, linhas, fonte_texto, 560, COR_CINZA_CLARO, espacamento_linha=12, alinhamento="center")

    _desenhar_rodape(draw, total_slides, total_slides)
    return img


def criar_carrossel(item):
    ig = item.get("instagram", {}) or {}
    headline = item.get("headline", "Antes do Sino")

    imagens = [criar_slide_capa(headline, ig.get("hook") or headline)]

    blocos = [
        ("O QUE ACONTECEU?", ig.get("context", "")),
        ("POR QUE O MERCADO REAGIU?", ig.get("why_it_matters", "")),
        ("IMPACTO NO MERCADO", ig.get("impact", "")),
        ("O QUE MONITORAR AGORA?", ig.get("watch_next", "")),
    ]
    numero = 2
    total = 2 + len([b for b in blocos if b[1]]) + 1
    for cabecalho, corpo in blocos:
        if not corpo:
            continue
        imagens.append(criar_slide_conteudo(numero, cabecalho, corpo, total))
        numero += 1

    imagens.append(criar_slide_encerramento(ig.get("cta") or "Acompanhe o mercado no Antes do Sino.", total))
    return imagens


# ---------------------------------------------------------------------------
# CARD (templates "quick_insight" e "market_snapshot") - imagem unica
# ---------------------------------------------------------------------------

def criar_card_simples(item):
    ig = item.get("instagram", {}) or {}
    headline = item.get("headline", "Antes do Sino")
    linha_apoio = ig.get("context") or ig.get("hook") or ""

    img, draw = _base_slide()
    fonte_marca = carregar_fonte(28, negrito=True)
    fonte_titulo = carregar_fonte(52, negrito=True)
    fonte_apoio = carregar_fonte(32, negrito=False)

    draw.text((MARGEM, MARGEM), "ANTES DO SINO", font=fonte_marca, fill=COR_AZUL)
    draw.line([(MARGEM, MARGEM + 50), (MARGEM + 80, MARGEM + 50)], fill=COR_AZUL, width=4)

    linhas_titulo = quebrar_texto(draw, headline, fonte_titulo, TAMANHO_CANVAS - 2 * MARGEM)
    y = 420
    y = desenhar_linhas(draw, linhas_titulo, fonte_titulo, y, COR_BRANCO, espacamento_linha=12)

    if linha_apoio:
        y += 30
        linhas_apoio = quebrar_texto(draw, linha_apoio, fonte_apoio, TAMANHO_CANVAS - 2 * MARGEM)
        desenhar_linhas(draw, linhas_apoio, fonte_apoio, y, COR_CINZA_CLARO, espacamento_linha=10)

    _desenhar_rodape(draw, 1, 1)
    return [img]


# ---------------------------------------------------------------------------
# TikTok - roteiro estruturado (texto), nao video nesta fase
# ---------------------------------------------------------------------------

def formatar_roteiro_tiktok(item, pasta):
    tk = item.get("tiktok", {}) or {}
    cenas = tk.get("scenes", [])
    cta = tk.get("cta", "")

    linhas = ["ROTEIRO TIKTOK/REELS - " + item.get("headline", ""), ""]
    for i, cena in enumerate(cenas, start=1):
        linhas.append("Cena " + str(i) + ":")
        linhas.append("  Visual: " + cena.get("visual", ""))
        linhas.append("  Fala: " + cena.get("line", ""))
        linhas.append("")
    if cta:
        linhas.append("Encerramento: " + cta)

    caminho = os.path.join(pasta, "tiktok_roteiro.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
    return caminho


# ---------------------------------------------------------------------------
# Orquestracao - decide o tipo de ativo pelo TEMPLATE, nunca pelo modo
# ---------------------------------------------------------------------------

def gerar_ativo_visual(item):
    """Consulta a tabela LOCAL (content_template -> tipo de ativo) e
    gera o Instagram no formato certo, alem do roteiro do TikTok.
    Nunca assume 'sempre carrossel' - decide pelo template do item."""
    content_template = item.get("content_template", "quick_insight")
    tipo_ativo = DESIGN_MAP.get(content_template, "card")

    data = item.get("date") or datetime.now(BR_TZ).strftime("%Y-%m-%d")
    slug = slugify_local(item.get("headline", "tema"))
    pasta = os.path.join(SOCIAL_POSTS_DIR, data + "_" + slug)
    os.makedirs(pasta, exist_ok=True)

    if tipo_ativo == "carousel":
        imagens = criar_carrossel(item)
    else:
        imagens = criar_card_simples(item)

    for i, img in enumerate(imagens, start=1):
        caminho_arquivo = os.path.join(pasta, "slide_" + str(i).zfill(2) + ".png")
        img.save(caminho_arquivo, "PNG")

    formatar_roteiro_tiktok(item, pasta)

    return pasta, len(imagens), tipo_ativo


# ---------------------------------------------------------------------------
# Persistencia - le/atualiza a MESMA fila do content engine
# ---------------------------------------------------------------------------

def _load_social_queue():
    if os.path.exists(SOCIAL_QUEUE_FILE):
        try:
            with open(SOCIAL_QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def _save_social_queue(fila):
    os.makedirs(os.path.dirname(SOCIAL_QUEUE_FILE), exist_ok=True)
    with open(SOCIAL_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(fila, f, ensure_ascii=False, indent=2)


def _encontrar_itens_aprovados_pendentes(fila):
    """Todos os itens com status == 'approved' ainda sem design -
    qualquer modo, sem excecao (Midday incluso)."""
    indices = []
    for i, item in enumerate(fila):
        if item.get("status") == "approved":
            indices.append(i)
    return indices


# ---------------------------------------------------------------------------
# Notificacao privada - mesmo padrao/credenciais do content engine
# ---------------------------------------------------------------------------

def _registrar_transicao(item, novo_status, detalhe=""):
    """Duplicada de proposito (isolamento) - mesmo padrao do
    content_engine.py, registra toda mudanca de estado no historico."""
    item["status"] = novo_status
    historico = item.setdefault("history", [])
    historico.append({
        "status": novo_status,
        "at": datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "detalhe": detalhe,
    })
    return item


def notificar_admin_design(item, pasta, quantidade_slides, tipo_ativo):
    """Notificacao 'Arte pronta' - envia TODAS as imagens do carrossel
    (via album/sendMediaGroup, ate 10 fotos numa mensagem so) quando
    houver mais de 1 slide; envia foto unica (sendPhoto) quando for
    card. Legenda com o texto pronto pra copiar vai na PRIMEIRA
    imagem do album (e onde o Telegram exibe a legenda). Se o envio
    de imagem falhar por qualquer motivo, cai com seguranca para
    mensagem de texto simples - nunca perde o aviso."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Design Engine: TELEGRAM_ADMIN_CHAT_ID não configurado - aviso privado não enviado.")
        return

    plataforma = (item.get("platform") or "x").upper()
    texto_post = (item.get("x") or {}).get("post", "")
    legenda_instagram = item.get("instagram_caption", "")

    texto = (
        "✅ <b>Arte pronta</b>\n"
        "Assunto: " + item.get("headline", "") + "\n"
        "Formato: " + tipo_ativo + " (" + str(quantidade_slides) + " imagem(ns))\n\n"
        "Destino:\n☑ " + plataforma + " (publicação manual)\n\n"
    )
    if legenda_instagram:
        texto += "Legenda do Instagram:\n" + legenda_instagram + "\n\n"
    if texto_post:
        texto += "Texto pronto para copiar (X):\n" + texto_post + "\n\n"
    texto += (
        "ID: <code>" + item.get("id", "") + "</code>\n\n"
        "Depois de publicar manualmente, responder:\nPublicado " + item.get("id", "")
        + "\n(opcional: cole o link do post depois do ID)"
    )

    caminhos_slides = sorted(
        os.path.join(pasta, f) for f in os.listdir(pasta)
        if f.startswith("slide_") and f.endswith(".png")
    ) if os.path.isdir(pasta) else []

    try:
        if len(caminhos_slides) >= 2:
            _enviar_album_telegram(caminhos_slides, texto)
        elif len(caminhos_slides) == 1:
            url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
            with open(caminhos_slides[0], "rb") as f:
                files = {"photo": f}
                data = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "caption": texto, "parse_mode": "HTML"}
                requests.post(url, data=data, files=files, timeout=20)
        else:
            url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
            payload = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": texto, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Erro ao enviar notificação privada do design engine (isolado): " + str(e))


def _enviar_album_telegram(caminhos_imagens, legenda):
    """Envia varias imagens juntas via sendMediaGroup (ate 10 por
    mensagem - todos os nossos carrosseis, com 5-7 slides, cabem
    tranquilo). A legenda so pode ir em 1 item do album - o Telegram
    exibe a legenda do PRIMEIRO item como legenda do album inteiro."""
    import json as json_module

    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMediaGroup"

    media = []
    files = {}
    for i, caminho in enumerate(caminhos_imagens[:10]):
        chave_arquivo = "foto" + str(i)
        item_media = {"type": "photo", "media": "attach://" + chave_arquivo}
        if i == 0:
            item_media["caption"] = legenda
            item_media["parse_mode"] = "HTML"
        media.append(item_media)
        files[chave_arquivo] = open(caminho, "rb")

    try:
        data = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "media": json_module.dumps(media)}
        requests.post(url, data=data, files=files, timeout=30)
    finally:
        for f in files.values():
            f.close()


def notificar_falha_design(item, erro):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        return
    texto = (
        "❌ <b>Falha ao gerar arte</b>\n\n"
        "Assunto: " + item.get("headline", "") + "\n"
        "ID: <code>" + item.get("id", "") + "</code>\n"
        "Erro: " + str(erro)
    )
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        payload = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": texto, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Erro ao enviar notificação de falha de design (isolado): " + str(e))


# ---------------------------------------------------------------------------
# Ponto de entrada unico
# ---------------------------------------------------------------------------

def process_pending_designs():
    """Processa TODO item com status == 'approved', de QUALQUER modo -
    sem excecao para Midday. Ao terminar, marca status = 'designed'.
    Se a geracao falhar, o item NUNCA fica travado silenciosamente em
    'approved' - vira 'failed', com o erro registrado e notificado."""
    fila = _load_social_queue()
    indices_pendentes = _encontrar_itens_aprovados_pendentes(fila)

    if not indices_pendentes:
        return

    for indice in indices_pendentes:
        item = fila[indice]
        _registrar_transicao(item, "designing", "Gerando ativo visual")
        fila[indice] = item
        _save_social_queue(fila)  # salva o estado 'designing' ANTES de tentar gerar

        try:
            pasta, quantidade, tipo_ativo = gerar_ativo_visual(item)

            fila = _load_social_queue()
            indice = next((i for i, it in enumerate(fila) if it.get("id") == item.get("id")), indice)
            item = fila[indice]
            item["design_folder"] = pasta
            _registrar_transicao(item, "designed", "Ativo visual gerado com sucesso")
            fila[indice] = item
            _save_social_queue(fila)

            print(
                "Social Design Engine: item " + item.get("id", "") + " desenhado ("
                + tipo_ativo + ", " + str(quantidade) + " imagem(ns)) em " + pasta
            )
            notificar_admin_design(item, pasta, quantidade, tipo_ativo)
        except Exception as e:
            print("Erro no Social Design Engine ao processar item " + item.get("id", "") + " (isolado): " + str(e))
            fila = _load_social_queue()
            indice = next((i for i, it in enumerate(fila) if it.get("id") == item.get("id")), indice)
            item = fila[indice]
            item["design_error"] = str(e)
            _registrar_transicao(item, "failed", "Falha ao gerar arte: " + str(e))
            fila[indice] = item
            _save_social_queue(fila)
            notificar_falha_design(item, str(e))
            continue
