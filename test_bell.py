"""
Script de TESTE isolado - nao faz parte do bot principal.
Gera uma unica imagem de teste usando o SVG exato do sino que ja esta
no site, convertido via cairosvg, e composto sobre o fundo padrao com
Pillow. Salva em docs/test-bell.png para visualizar no navegador.
"""

import cairosvg
from PIL import Image, ImageDraw, ImageFont
import io

W, H = 1080, 1080

BELL_SVG = """
<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="200" height="200">
<path d="M12 2v2M8.5 20a3.5 3.5 0 0 0 7 0M5 17h14l-1.4-2.1A7 7 0 0 1 16.5 11V9a4.5 4.5 0 0 0-9 0v2a7 7 0 0 1-1.1 3.9L5 17Z" stroke="#F2C879" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""

navy_light = (20, 44, 82)
navy_deep = (5, 13, 26)
gold = (242, 200, 121)
cream = (245, 239, 227)
slate = (124, 140, 166)

img = Image.new("RGB", (W, H), navy_deep)
draw = ImageDraw.Draw(img)

for y in range(H):
    ratio = y / H
    r = int(navy_light[0] + (navy_deep[0] - navy_light[0]) * ratio)
    g = int(navy_light[1] + (navy_deep[1] - navy_light[1]) * ratio)
    b = int(navy_light[2] + (navy_deep[2] - navy_light[2]) * ratio)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# Converte o SVG do sino em PNG (com transparencia) via cairosvg
bell_png_bytes = cairosvg.svg2png(bytestring=BELL_SVG.encode("utf-8"), output_width=200, output_height=200)
bell_img = Image.open(io.BytesIO(bell_png_bytes)).convert("RGBA")

# Cola o sino centralizado no topo da imagem
bell_x = (W - bell_img.width) // 2
bell_y = 220
img.paste(bell_img, (bell_x, bell_y), bell_img)

font_bold = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 58)
font_regular = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 34)


def draw_centered_text(draw, text, y, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (W - text_w) / 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1]) + 20


y = bell_y + bell_img.height + 40
y = draw_centered_text(draw, "ANTES DO SINO", y, font_bold, cream)
y = draw_centered_text(draw, "Teste com SVG real do site", y, font_regular, slate)

img.save("docs/test-bell.png")
print("Imagem de teste salva em docs/test-bell.png")
