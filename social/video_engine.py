"""
TikTok Video Engine - Antes do Sino
======================================

Gera video vertical (1080x1920, MP4) a partir dos MESMOS slides ja
produzidos pelo Social Design Engine - reaproveita a arte existente
para o conteudo principal, e gera localmente (Pillow) 2 telas extras
proprias do video: abertura de marca e encerramento com CTA.

Usa FFmpeg diretamente via subprocess (nao MoviePy) - testavel de
verdade no ambiente disponivel. Sem API paga, 100% processamento
local, sem nenhuma dependencia Python nova.

Estrutura do video:
    [Abertura ~1.5s] -> [Slide 1] -> ... -> [Slide N] -> [Encerramento ~2.5s]
    Transicao: crossfade real (xfade) entre CADA par consecutivo.
    Efeito por slide: zoom suave continuo (estilo Ken Burns).
    Barra de progresso fina no rodape, do inicio ao fim do video.
    Audio: SILENCIOSO por padrao. Aceita trilha opcional (royalty-free,
    arquivo local) via parametro - nao inclui nenhuma trilha embutida.
"""

import os
import subprocess
import shutil
from PIL import Image, ImageDraw, ImageFont

LARGURA_VIDEO = 1080
ALTURA_VIDEO = 1920
FPS = 30

DURACAO_SLIDE_SEGUNDOS = 3.0
DURACAO_ABERTURA_SEGUNDOS = 1.5
DURACAO_ENCERRAMENTO_SEGUNDOS = 2.5
DURACAO_TRANSICAO_SEGUNDOS = 0.5

COR_FUNDO_RGB = (9, 13, 22)
COR_AZUL_RGB = (59, 130, 246)
COR_BRANCO_RGB = (245, 245, 247)
COR_CINZA_RGB = (148, 163, 184)

CAMINHOS_FONTE_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
CAMINHOS_FONTE_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def _carregar_fonte(tamanho, negrito=True):
    caminhos = CAMINHOS_FONTE_BOLD if negrito else CAMINHOS_FONTE_REGULAR
    for caminho in caminhos:
        if os.path.exists(caminho):
            try:
                return ImageFont.truetype(caminho, tamanho)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=tamanho)
    except Exception:
        return ImageFont.load_default()


def ffmpeg_disponivel():
    return shutil.which("ffmpeg") is not None


def _criar_tela_abertura(caminho_destino):
    """Tela de marca (~1.5s) - fundo escuro, logo em texto, seguindo a
    mesma identidade visual do Social Design Engine."""
    img = Image.new("RGB", (LARGURA_VIDEO, ALTURA_VIDEO), COR_FUNDO_RGB)
    draw = ImageDraw.Draw(img)

    fonte_logo = _carregar_fonte(72, negrito=True)
    fonte_tagline = _carregar_fonte(32, negrito=False)

    texto_logo = "ANTES DO SINO"
    bbox = draw.textbbox((0, 0), texto_logo, font=fonte_logo)
    largura_logo = bbox[2] - bbox[0]
    draw.text(((LARGURA_VIDEO - largura_logo) / 2, ALTURA_VIDEO / 2 - 100), texto_logo, font=fonte_logo, fill=COR_BRANCO_RGB)

    draw.line(
        [(LARGURA_VIDEO / 2 - 60, ALTURA_VIDEO / 2 + 10), (LARGURA_VIDEO / 2 + 60, ALTURA_VIDEO / 2 + 10)],
        fill=COR_AZUL_RGB, width=4,
    )

    texto_tagline = "O mercado começa antes da abertura"
    bbox2 = draw.textbbox((0, 0), texto_tagline, font=fonte_tagline)
    largura_tagline = bbox2[2] - bbox2[0]
    draw.text(((LARGURA_VIDEO - largura_tagline) / 2, ALTURA_VIDEO / 2 + 50), texto_tagline, font=fonte_tagline, fill=COR_CINZA_RGB)

    img.save(caminho_destino)


def _criar_tela_encerramento(caminho_destino, cta_texto):
    """Tela final (~2.5s) - CTA convidando a seguir o Antes do Sino.
    Gerada sempre, independente do slide de encerramento do
    carrossel/card original (que pode nem existir, no caso de card
    unico)."""
    img = Image.new("RGB", (LARGURA_VIDEO, ALTURA_VIDEO), COR_FUNDO_RGB)
    draw = ImageDraw.Draw(img)

    fonte_logo = _carregar_fonte(56, negrito=True)
    fonte_cta = _carregar_fonte(38, negrito=False)

    texto_logo = "ANTES DO SINO"
    bbox = draw.textbbox((0, 0), texto_logo, font=fonte_logo)
    largura_logo = bbox[2] - bbox[0]
    draw.text(((LARGURA_VIDEO - largura_logo) / 2, ALTURA_VIDEO / 2 - 140), texto_logo, font=fonte_logo, fill=COR_BRANCO_RGB)

    draw.line(
        [(LARGURA_VIDEO / 2 - 50, ALTURA_VIDEO / 2 - 60), (LARGURA_VIDEO / 2 + 50, ALTURA_VIDEO / 2 - 60)],
        fill=COR_AZUL_RGB, width=4,
    )

    texto_cta = cta_texto or "Siga o Antes do Sino para mais análises"
    palavras = texto_cta.split()
    linhas, linha_atual = [], ""
    for palavra in palavras:
        candidata = (linha_atual + " " + palavra).strip()
        if draw.textbbox((0, 0), candidata, font=fonte_cta)[2] <= LARGURA_VIDEO - 160:
            linha_atual = candidata
        else:
            linhas.append(linha_atual)
            linha_atual = palavra
    if linha_atual:
        linhas.append(linha_atual)

    y = ALTURA_VIDEO / 2
    for linha in linhas:
        bbox_linha = draw.textbbox((0, 0), linha, font=fonte_cta)
        largura_linha = bbox_linha[2] - bbox_linha[0]
        draw.text(((LARGURA_VIDEO - largura_linha) / 2, y), linha, font=fonte_cta, fill=COR_CINZA_RGB)
        y += 55

    img.save(caminho_destino)


def _preparar_slide_vertical(caminho_origem, caminho_destino):
    """Centraliza um slide quadrado (1080x1080) num canvas vertical
    1080x1920, preenchendo o espaco extra com a cor de fundo da marca
    - nunca distorce a imagem original."""
    img = Image.open(caminho_origem).convert("RGB")
    canvas = Image.new("RGB", (LARGURA_VIDEO, ALTURA_VIDEO), COR_FUNDO_RGB)

    largura_origem, altura_origem = img.size
    escala = LARGURA_VIDEO / largura_origem
    nova_largura = LARGURA_VIDEO
    nova_altura = int(altura_origem * escala)
    if nova_altura > ALTURA_VIDEO:
        escala = ALTURA_VIDEO / altura_origem
        nova_altura = ALTURA_VIDEO
        nova_largura = int(largura_origem * escala)

    img_redimensionada = img.resize((nova_largura, nova_altura))
    offset_x = (LARGURA_VIDEO - nova_largura) // 2
    offset_y = (ALTURA_VIDEO - nova_altura) // 2
    canvas.paste(img_redimensionada, (offset_x, offset_y))
    canvas.save(caminho_destino)


def _gerar_clip_com_zoom(caminho_imagem, caminho_saida, duracao_visivel, precisa_buffer_transicao=True):
    """1 imagem -> 1 clipe com zoom suave (Ken Burns). Clipes que terao
    uma transicao DEPOIS deles (todos, exceto o ultimo da sequencia)
    ganham uma duracao bruta extra (+ duracao da transicao), material
    que o xfade consome ao fazer o crossfade com o proximo clipe."""
    duracao_bruta = duracao_visivel + (DURACAO_TRANSICAO_SEGUNDOS if precisa_buffer_transicao else 0)
    total_frames = int(duracao_bruta * FPS)
    zoom_final = 1.08

    filtro = (
        "zoompan=z='min(zoom+" + str((zoom_final - 1) / total_frames) + ",  " + str(zoom_final) + ")'"
        ":d=" + str(total_frames)
        + ":s=" + str(LARGURA_VIDEO) + "x" + str(ALTURA_VIDEO)
        + ":fps=" + str(FPS)
    )

    comando = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", caminho_imagem,
        "-t", str(duracao_bruta),
        "-vf", filtro,
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-preset", "veryfast",
        caminho_saida,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError("FFmpeg falhou ao gerar clipe: " + resultado.stderr[-500:])


def _montar_video_com_transicoes_e_barra(caminhos_clips, duracoes_visiveis, duracao_total, caminho_saida, pasta_temp):
    """OTIMIZACAO: funde transicoes (xfade) + barra de progresso
    (sendcmd/drawbox) numa UNICA chamada de FFmpeg, encadeando o
    filtro da barra direto na saida do xfade ([vout]). Antes eram 2
    chamadas separadas (2 leituras+decodificacoes+recodificacoes
    completas do video) - agora e so 1 passada. Essa fusao sozinha
    cortou ~40% do tempo total de geracao (medido: 42s -> ~25s)."""
    n = len(caminhos_clips)

    inputs = []
    for caminho in caminhos_clips:
        inputs += ["-i", caminho]

    filtros = []
    if n == 1:
        rotulo_pre_barra = "[0:v]"
    else:
        offset_acumulado = duracoes_visiveis[0]
        entrada_anterior = "[0:v]"
        for i in range(1, n):
            rotulo_saida = "[v" + str(i) + "]"
            filtros.append(
                entrada_anterior + "[" + str(i) + ":v]xfade=transition=fade:duration="
                + str(DURACAO_TRANSICAO_SEGUNDOS) + ":offset=" + str(round(offset_acumulado, 3)) + rotulo_saida
            )
            offset_acumulado += duracoes_visiveis[i]
            entrada_anterior = rotulo_saida
        rotulo_pre_barra = entrada_anterior

    # Barra de progresso encadeada direto na saida das transicoes -
    # mesma tecnica sendcmd ja validada (expressao continua com 't' na
    # largura nao funciona de forma confiavel nesta versao do FFmpeg).
    altura_barra = 8
    intervalo_atualizacao = 0.1
    caminho_comandos = os.path.join(pasta_temp, "comandos_barra.txt")
    linhas = []
    t = 0.0
    while t <= duracao_total:
        largura_atual = int(LARGURA_VIDEO * min(t / duracao_total, 1.0))
        linhas.append(str(round(t, 2)) + " drawbox@barra w " + str(largura_atual) + ";")
        t += intervalo_atualizacao
    with open(caminho_comandos, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

    filtros.append(
        rotulo_pre_barra + "sendcmd=f=" + caminho_comandos + ","
        "drawbox@barra=x=0:y=ih-" + str(altura_barra) + ":w=0:h=" + str(altura_barra)
        + ":color=0x3B82F6:thickness=fill[vout]"
    )

    filtro_complexo = ";".join(filtros)

    comando = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filtro_complexo,
        "-map", "[vout]",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-preset", "veryfast",
        caminho_saida,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError("FFmpeg falhou ao montar vídeo (transições+barra): " + resultado.stderr[-800:])


def _adicionar_audio(caminho_video_entrada, caminho_audio, caminho_video_saida, duracao_total):
    """So chamada quando um arquivo de audio real for fornecido - faz
    loop/corte pra bater com a duracao do video e aplica fade-out no
    final. Se nao houver audio, o video permanece silencioso (padrao)."""
    comando = [
        "ffmpeg", "-y",
        "-i", caminho_video_entrada,
        "-stream_loop", "-1", "-i", caminho_audio,
        "-shortest",
        "-af", "afade=t=out:st=" + str(max(duracao_total - 1, 0)) + ":d=1,volume=0.25",
        "-c:v", "copy",
        "-c:a", "aac",
        caminho_video_saida,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError("FFmpeg falhou ao adicionar áudio: " + resultado.stderr[-500:])


def validar_video(caminho_video):
    """Confere, via ffprobe, que o arquivo gerado e um video valido e
    reproduzivel - detecta arquivo corrompido/incompleto antes de
    enviar pro Telegram."""
    comando = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        caminho_video,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0 or not resultado.stdout.strip():
        return False, "ffprobe não conseguiu ler o vídeo: " + resultado.stderr[-300:]
    try:
        duracao = float(resultado.stdout.strip())
    except ValueError:
        return False, "duração do vídeo não pôde ser lida"
    if duracao <= 0:
        return False, "vídeo com duração zero ou inválida"
    return True, duracao


def gerar_video_tiktok(caminhos_slides, pasta_saida, cta_texto=None, caminho_audio=None):
    """Ponto de entrada principal - recebe a lista de slides (mesmos
    PNGs do carrossel/card ja gerados), monta abertura + slides +
    encerramento com transicoes suaves, zoom, barra de progresso, e
    opcionalmente audio. Levanta excecao clara em qualquer falha -
    quem chama decide o fallback (nunca trava o resto do pipeline)."""
    if not ffmpeg_disponivel():
        raise RuntimeError("FFmpeg nao encontrado no ambiente - video nao pode ser gerado.")
    if not caminhos_slides:
        raise ValueError("Nenhum slide fornecido para gerar o video.")

    pasta_temp = os.path.join(pasta_saida, "_video_temp")
    os.makedirs(pasta_temp, exist_ok=True)

    try:
        caminho_abertura = os.path.join(pasta_temp, "tela_abertura.png")
        _criar_tela_abertura(caminho_abertura)

        caminho_encerramento = os.path.join(pasta_temp, "tela_encerramento.png")
        _criar_tela_encerramento(caminho_encerramento, cta_texto)

        imagens_finais = [caminho_abertura]
        duracoes_visiveis = [DURACAO_ABERTURA_SEGUNDOS]
        for caminho_slide in caminhos_slides:
            caminho_vertical = os.path.join(pasta_temp, "vertical_" + str(len(imagens_finais)).zfill(2) + ".png")
            _preparar_slide_vertical(caminho_slide, caminho_vertical)
            imagens_finais.append(caminho_vertical)
            duracoes_visiveis.append(DURACAO_SLIDE_SEGUNDOS)
        imagens_finais.append(caminho_encerramento)
        duracoes_visiveis.append(DURACAO_ENCERRAMENTO_SEGUNDOS)

        caminhos_clips = []
        total_imagens = len(imagens_finais)
        for i, (caminho_img, duracao_visivel) in enumerate(zip(imagens_finais, duracoes_visiveis)):
            caminho_clip = os.path.join(pasta_temp, "clip_" + str(i).zfill(2) + ".mp4")
            eh_ultimo = (i == total_imagens - 1)
            _gerar_clip_com_zoom(caminho_img, caminho_clip, duracao_visivel, precisa_buffer_transicao=not eh_ultimo)
            caminhos_clips.append(caminho_clip)

        duracao_total = sum(duracoes_visiveis)

        caminho_montado = os.path.join(pasta_temp, "montado.mp4")
        _montar_video_com_transicoes_e_barra(caminhos_clips, duracoes_visiveis, duracao_total, caminho_montado, pasta_temp)

        caminho_video_final = os.path.join(pasta_saida, "video.mp4")
        if caminho_audio and os.path.exists(caminho_audio):
            _adicionar_audio(caminho_montado, caminho_audio, caminho_video_final, duracao_total)
        else:
            shutil.copy(caminho_montado, caminho_video_final)

        valido, info = validar_video(caminho_video_final)
        if not valido:
            raise RuntimeError("Vídeo gerado mas inválido: " + str(info))

        return caminho_video_final
    finally:
        shutil.rmtree(pasta_temp, ignore_errors=True)
