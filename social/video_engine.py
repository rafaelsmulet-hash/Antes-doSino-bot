"""
TikTok Video Engine - Antes do Sino
======================================

Gera video vertical (1080x1920, MP4) a partir dos MESMOS slides ja
produzidos pelo Social Design Engine - reaproveita 100% da arte,
nao gera nada novo visualmente do zero.

Usa FFmpeg diretamente via subprocess (nao MoviePy) - o ambiente de
desenvolvimento nao tinha acesso a internet para instalar/validar o
MoviePy, mas o FFmpeg ja esta confirmado disponivel e testavel. Sem
API paga, 100% processamento local.

Efeitos aplicados por slide: zoom suave continuo (estilo Ken Burns) +
fade de entrada/saida. Slides concatenados em sequencia.
"""

import os
import subprocess
import shutil
from PIL import Image

LARGURA_VIDEO = 1080
ALTURA_VIDEO = 1920
FPS = 30
DURACAO_POR_SLIDE_SEGUNDOS = 3.0
DURACAO_FADE_SEGUNDOS = 0.4

COR_FUNDO_RGB = (9, 13, 22)  # mesma cor de fundo da identidade visual


def ffmpeg_disponivel():
    return shutil.which("ffmpeg") is not None


def _preparar_slide_vertical(caminho_origem, caminho_destino):
    """Centraliza o slide quadrado (1080x1080) num canvas vertical
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


def _gerar_clip_por_slide(caminho_slide_vertical, caminho_clip_saida, duracao):
    """1 slide -> 1 clipe curto com zoom suave (Ken Burns) + fade de
    entrada/saida, via filtro zoompan + fade do proprio FFmpeg."""
    total_frames = int(duracao * FPS)
    zoom_final = 1.08

    filtro = (
        "zoompan=z='min(zoom+" + str((zoom_final - 1) / total_frames) + ",  " + str(zoom_final) + ")'"
        ":d=" + str(total_frames)
        + ":s=" + str(LARGURA_VIDEO) + "x" + str(ALTURA_VIDEO)
        + ":fps=" + str(FPS)
        + ",fade=t=in:st=0:d=" + str(DURACAO_FADE_SEGUNDOS)
        + ",fade=t=out:st=" + str(duracao - DURACAO_FADE_SEGUNDOS) + ":d=" + str(DURACAO_FADE_SEGUNDOS)
    )

    comando = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", caminho_slide_vertical,
        "-t", str(duracao),
        "-vf", filtro,
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        caminho_clip_saida,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError("FFmpeg falhou ao gerar clipe do slide: " + resultado.stderr[-500:])


def _concatenar_clips(caminhos_clips, caminho_video_final):
    """Concatena os clipes em sequencia (cada um ja tem seu proprio
    fade de entrada/saida, entao a transicao fica suave sem precisar
    de xfade com calculo de offset acumulado)."""
    pasta_temp = os.path.dirname(caminhos_clips[0])
    lista_path = os.path.join(pasta_temp, "lista_concat.txt")
    with open(lista_path, "w", encoding="utf-8") as f:
        for caminho in caminhos_clips:
            f.write("file '" + os.path.abspath(caminho) + "'\n")

    comando = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", lista_path,
        "-c", "copy",
        caminho_video_final,
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError("FFmpeg falhou ao concatenar clipes: " + resultado.stderr[-500:])


def gerar_video_tiktok(caminhos_slides, pasta_saida):
    """Ponto de entrada principal - recebe a lista de slides (mesmos
    PNGs do carrossel/card ja gerados) e produz video.mp4 em
    pasta_saida. Levanta excecao clara em qualquer falha - quem chama
    decide o fallback (nunca trava o resto do pipeline)."""
    if not ffmpeg_disponivel():
        raise RuntimeError("FFmpeg nao encontrado no ambiente - video nao pode ser gerado.")

    if not caminhos_slides:
        raise ValueError("Nenhum slide fornecido para gerar o video.")

    pasta_temp = os.path.join(pasta_saida, "_video_temp")
    os.makedirs(pasta_temp, exist_ok=True)

    try:
        caminhos_clips = []
        for i, caminho_slide in enumerate(caminhos_slides):
            caminho_vertical = os.path.join(pasta_temp, "vertical_" + str(i).zfill(2) + ".png")
            _preparar_slide_vertical(caminho_slide, caminho_vertical)

            caminho_clip = os.path.join(pasta_temp, "clip_" + str(i).zfill(2) + ".mp4")
            _gerar_clip_por_slide(caminho_vertical, caminho_clip, DURACAO_POR_SLIDE_SEGUNDOS)
            caminhos_clips.append(caminho_clip)

        caminho_video_final = os.path.join(pasta_saida, "video.mp4")
        _concatenar_clips(caminhos_clips, caminho_video_final)

        return caminho_video_final
    finally:
        shutil.rmtree(pasta_temp, ignore_errors=True)
