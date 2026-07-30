"""
Social Design Engine - Antes do Sino (Fase 2)
================================================

Modulo TOTALMENTE ISOLADO - nao importa nada de main.py nem de
social_content_engine.py. Le o conteudo JA GERADO em
docs/social_queue.json e transforma o texto em artes (PNG 1080x1080),
usando so Python + Pillow. Sem IA de imagem, sem API paga, sem custo
externo.

Responsabilidade unica: texto -> imagem. NAO escolhe assunto, NAO
gera texto, NAO decide quando publicar. Isso e tudo do
social_content_engine.py, que continua sem nenhuma alteracao de logica.

Fluxo:
    docs/social_queue.json (item content_mode="closing" mais recente
    ainda nao desenhado)
        -> gerar_carrossel_visual()
        -> docs/social_posts/{data}_{slug-do-tema}/slide_01.png ... slide_06.png
        -> notificacao privada no Telegram (mesmo bot/admin da Fase 1)
        -> marca o item como "design_generated" no proprio social_queue.json
           (so para nao re-desenhar o mesmo item nos proximos ciclos)
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

# Caminhos de fonte tentados em ordem - se nenhum existir, cai no
# fallback padrao do Pillow (nunca quebra por fonte ausente).
CAMINHOS_FONTE_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
CAMINHOS_FONTE_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def carregar_fonte(tamanho, negrito=True):
    """Tenta carregar uma fonte TrueType de um caminho conhecido: se
    nenhuma existir no ambiente (ex: runner do GitHub Actions com
    fontes diferentes), cai no fallback padrao do Pillow - nunca
    lanca excecao por fonte ausente."""
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
    """Slug simples e isolado (sem depender de main.py) - remove
    acento via unicodedata (biblioteca padrao) e troca qualquer
    caractere fora de a-z0-9 por hifen."""
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
    """Quebra 'texto' em uma lista de linhas que cabem em
    'largura_maxima' pixels, usando a fonte informada. Funciona para
    texto de qualquer tamanho - palavra isolada maior que a largura
    maxima e colocada sozinha na linha (nunca trava)."""
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
    """Desenha uma lista de linhas ja quebradas, uma abaixo da outra.
    Retorna o Y final (util para posicionar o proximo bloco)."""
    y = y_inicio
    for linha in linhas:
        bbox = draw.textbbox((0, 0), linha, font=fonte)
        largura_linha = bbox[2] - bbox[0]
        altura_linha = bbox[3] - bbox[1]
        if alinhamento == "center":
            x = (largura_canvas - largura_linha) / 2
        else:
            x = MARGEM
        draw.text((x, y), linha, font=fonte, fill=cor)
        y += altura_linha + espacamento_linha
    return y


def _base_slide():
    """Canvas base comum a todo slide - fundo escuro + numero/marca de
    rodape, que sao sempre iguais."""
    img = Image.new("RGB", (TAMANHO_CANVAS, TAMANHO_CANVAS), COR_FUNDO)
    draw = ImageDraw.Draw(img)
    return img, draw


def _desenhar_rodape(draw, numero_slide, total_slides=6):
    fonte_rodape = carregar_fonte(22, negrito=False)
    texto_rodape = "ANTES DO SINO"
    draw.text((MARGEM, TAMANHO_CANVAS - 70), texto_rodape, font=fonte_rodape, fill=COR_CINZA)

    texto_numero = str(numero_slide).zfill(2) + "/" + str(total_slides).zfill(2)
    bbox = draw.textbbox((0, 0), texto_numero, font=fonte_rodape)
    largura = bbox[2] - bbox[0]
    draw.text((TAMANHO_CANVAS - MARGEM - largura, TAMANHO_CANVAS - 70), texto_numero, font=fonte_rodape, fill=COR_CINZA)

    # Linha divisoria fina, elemento "azul/cinza" da identidade visual
    draw.line(
        [(MARGEM, TAMANHO_CANVAS - 100), (TAMANHO_CANVAS - MARGEM, TAMANHO_CANVAS - 100)],
        fill=COR_CINZA, width=2,
    )


def criar_slide_capa(topico, gancho):
    """Slide 1 - nome do canal, titulo do assunto, gancho forte."""
    img, draw = _base_slide()

    fonte_marca = carregar_fonte(30, negrito=True)
    fonte_titulo = carregar_fonte(64, negrito=True)
    fonte_gancho = carregar_fonte(34, negrito=False)

    draw.text((MARGEM, MARGEM), "ANTES DO SINO", font=fonte_marca, fill=COR_AZUL)
    draw.line([(MARGEM, MARGEM + 55), (MARGEM + 90, MARGEM + 55)], fill=COR_AZUL, width=4)

    linhas_titulo = quebrar_texto(draw, topico, fonte_titulo, TAMANHO_CANVAS - 2 * MARGEM)
    y = 340
    y = desenhar_linhas(draw, linhas_titulo, fonte_titulo, y, COR_BRANCO, espacamento_linha=14)

    y += 40
    linhas_gancho = quebrar_texto(draw, gancho, fonte_gancho, TAMANHO_CANVAS - 2 * MARGEM)
    desenhar_linhas(draw, linhas_gancho, fonte_gancho, y, COR_CINZA_CLARO, espacamento_linha=10)

    _desenhar_rodape(draw, 1)
    return img


def criar_slide_conteudo(numero_slide, cabecalho, corpo):
    """Slides 2 a 5 - cabecalho fixo do template + corpo vindo do
    conteudo ja gerado pela content engine. Reduz o tamanho da fonte
    do corpo automaticamente se o texto for longo demais para caber
    no espaco vertical disponivel - nunca deixa o texto invadir o
    rodape do slide."""
    img, draw = _base_slide()

    fonte_kicker = carregar_fonte(24, negrito=True)
    fonte_cabecalho = carregar_fonte(46, negrito=True)

    draw.text((MARGEM, MARGEM), "ANTES DO SINO", font=fonte_kicker, fill=COR_AZUL)

    y_titulo = MARGEM + 70
    linhas_cabecalho = quebrar_texto(draw, cabecalho, fonte_cabecalho, TAMANHO_CANVAS - 2 * MARGEM)
    y_apos_titulo = desenhar_linhas(draw, linhas_cabecalho, fonte_cabecalho, y_titulo, COR_AZUL, espacamento_linha=8)

    draw.line([(MARGEM, y_apos_titulo + 20), (TAMANHO_CANVAS - MARGEM, y_apos_titulo + 20)], fill=COR_CINZA, width=2)
    y_corpo_inicio = y_apos_titulo + 60

    espaco_disponivel = (TAMANHO_CANVAS - 130) - y_corpo_inicio  # 130 = area reservada ao rodape

    # Tenta tamanhos de fonte decrescentes ate o texto caber no espaco
    # vertical disponivel - garante que texto longo nunca invada o
    # rodape, sem nunca cortar palavra no meio.
    for tamanho_fonte in [38, 34, 30, 27, 24, 22]:
        fonte_corpo = carregar_fonte(tamanho_fonte, negrito=False)
        linhas_corpo = quebrar_texto(draw, corpo, fonte_corpo, TAMANHO_CANVAS - 2 * MARGEM)
        espacamento = 16 if tamanho_fonte >= 30 else 10
        altura_estimada = len(linhas_corpo) * (tamanho_fonte + espacamento + 8)
        if altura_estimada <= espaco_disponivel or tamanho_fonte == 22:
            desenhar_linhas(draw, linhas_corpo, fonte_corpo, y_corpo_inicio, COR_BRANCO, espacamento_linha=espacamento)
            break

    _desenhar_rodape(draw, numero_slide)
    return img


def criar_slide_encerramento(texto_final):
    """Slide 6 - encerramento com a identidade Antes do Sino."""
    img, draw = _base_slide()

    fonte_marca = carregar_fonte(52, negrito=True)
    fonte_texto = carregar_fonte(34, negrito=False)

    texto_marca = "ANTES DO SINO"
    bbox = draw.textbbox((0, 0), texto_marca, font=fonte_marca)
    largura_marca = bbox[2] - bbox[0]
    draw.text(((TAMANHO_CANVAS - largura_marca) / 2, 420), texto_marca, font=fonte_marca, fill=COR_BRANCO)

    draw.line(
        [(TAMANHO_CANVAS / 2 - 60, 500), (TAMANHO_CANVAS / 2 + 60, 500)],
        fill=COR_AZUL, width=4,
    )

    linhas = quebrar_texto(draw, texto_final, fonte_texto, TAMANHO_CANVAS - 2 * MARGEM)
    desenhar_linhas(draw, linhas, fonte_texto, 560, COR_CINZA_CLARO, espacamento_linha=12, alinhamento="center")

    _desenhar_rodape(draw, 6)
    return img


# ---------------------------------------------------------------------------
# Orquestracao - transforma o instagram_carousel (texto) em 6 PNGs
# ---------------------------------------------------------------------------

def gerar_carrossel_visual(item):
    """Recebe um item JA GERADO pelo social_content_engine (precisa
    ter 'instagram_carousel' com slide_1..slide_6) e produz 6 PNGs de
    1080x1080 em docs/social_posts/{data}_{slug}/.

    Nao escolhe assunto, nao gera texto - so transforma o que ja
    existe em imagem. Retorna o caminho da pasta gerada, ou None se o
    item nao tiver o conteudo necessario."""
    carrossel = item.get("instagram_carousel")
    if not isinstance(carrossel, dict):
        return None

    slides_texto = [carrossel.get("slide_" + str(i), "") for i in range(1, 7)]
    if not any(slides_texto):
        return None

    data = item.get("date") or datetime.now(BR_TZ).strftime("%Y-%m-%d")
    topico = item.get("topic", "Antes do Sino")
    slug = slugify_local(topico)
    pasta = os.path.join(SOCIAL_POSTS_DIR, data + "_" + slug)
    os.makedirs(pasta, exist_ok=True)

    cabecalhos = {
        2: "O QUE ACONTECEU?",
        3: "POR QUE O MERCADO REAGIU?",
        4: "IMPACTO NO MERCADO",
        5: "O QUE MONITORAR AGORA?",
    }

    imagens = []
    imagens.append(criar_slide_capa(topico, slides_texto[0] or topico))
    for numero in [2, 3, 4, 5]:
        imagens.append(criar_slide_conteudo(numero, cabecalhos[numero], slides_texto[numero - 1]))
    imagens.append(criar_slide_encerramento(slides_texto[5] or "Acompanhe o mercado no Antes do Sino."))

    for i, img in enumerate(imagens, start=1):
        caminho_arquivo = os.path.join(pasta, "slide_" + str(i).zfill(2) + ".png")
        img.save(caminho_arquivo, "PNG")

    return pasta


# ---------------------------------------------------------------------------
# Persistencia - le/atualiza a MESMA fila da Fase 1, so marcando o
# item como ja desenhado (nao mexe em nenhum outro campo)
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


def _encontrar_item_pendente(fila):
    """Procura, do mais recente para o mais antigo, o ultimo item
    content_mode='closing' que ainda nao teve arte gerada."""
    for i in range(len(fila) - 1, -1, -1):
        item = fila[i]
        if item.get("content_mode") == "closing" and not item.get("design_generated"):
            return i, item
    return None, None


# ---------------------------------------------------------------------------
# Notificacao privada - mesmo padrao/credenciais da Fase 1
# ---------------------------------------------------------------------------

def notificar_admin_design(topico, quantidade_slides, pasta):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID:
        print("Social Design Engine: TELEGRAM_ADMIN_CHAT_ID nao configurado - aviso privado nao enviado.")
        return

    texto = (
        "🎨 <b>Carrossel gerado</b>\n\n"
        "Tema: " + topico + "\n"
        "Slides: " + str(quantidade_slides) + "\n"
        "Local: " + pasta
    )
    try:
        url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
        payload = {"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": texto, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("Erro ao enviar notificacao privada do design engine (isolado): " + str(e))


# ---------------------------------------------------------------------------
# Ponto de entrada unico - e a UNICA funcao que o main.py precisa chamar
# ---------------------------------------------------------------------------

def process_latest_closing_content():
    """Le a fila, acha o item de fechamento mais recente ainda sem
    arte, gera o carrossel visual, notifica o admin, e marca o item
    como concluido (para nao redesenhar nos proximos ciclos)."""
    fila = _load_social_queue()
    indice, item = _encontrar_item_pendente(fila)
    if item is None:
        return

    pasta = gerar_carrossel_visual(item)
    if pasta is None:
        print("Social Design Engine: item sem instagram_carousel utilizavel - nada gerado.")
        return

    quantidade_slides = len([f for f in os.listdir(pasta) if f.endswith(".png")])

    fila[indice]["design_generated"] = True
    fila[indice]["design_folder"] = pasta
    _save_social_queue(fila)

    print(
        "Social Design Engine: carrossel gerado em " + pasta
        + " (" + str(quantidade_slides) + " slides, tema: " + item.get("topic", "") + ")"
    )

    notificar_admin_design(item.get("topic", ""), quantidade_slides, pasta)
