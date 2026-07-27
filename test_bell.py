"""
Script de TESTE isolado - versao 2, sino classico mais largo e solido.
"""

import cairosvg
from PIL import Image, ImageDraw, ImageFont
import io

W, H = 1080, 1080

# Sino classico estilo Font Awesome - mais largo, arredondado, solido
BELL_SVG = """
<svg viewBox="0 0 448 512" xmlns="http://www.w3.org/2000/svg" width="260" height="297">
<path fill="#F2C879" d="M224 0c-17.7 0-32 14.3-32 32V51.2C119 66 64 130.6 64 208v18.8c0 47-17.3 92.4-48.5 127.6l-7.4 8.3c-8.4 9.4-10.4 22.9-5.3 34.4S19.4 416 32 416H416c12.6 0 24-7.4 29.2-18.9s3.1-25-5.3-34.4l-7.4-8.3C401.3 319.2 384 273.9 384 226.8V208c0-77.4-55-142-128-156.8V32c0-17.7-14.3-32-32-32zm0 96c61.9 0 112 50.1 112 112v18.8c0 47.4 13.9 93.6 39.7 133.2H72.3C98.1 320.4 112 274.2 112 226.8V208c0-61.9 50.1-112 112-112zm64 384H160c0 17 6.7 33.3 18.7 45.3S224.9 512 224 512s33.3-6.7 45.3-18.7S288 465 288 448z"/>
</svg>
"""

navy_light = (20, 44, 82)
navy_deep = (5, 13, 26)
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

bell_png_bytes = cairosvg.svg2png(bytestring=BELL_SVG.encode("utf-8"), output_width=260, output_height=297)
bell_img = Image.open(io.BytesIO(bell_png_bytes)).convert("RGBA")

bell_x = (W - bell_img.width) // 2
bell_y = 200
img.paste(bell_img, (bell_x, bell_y), bell_img)

font_bold = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 58)
font_regular = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 34)


def draw_centered_text(draw, text, y, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (W - text_w) / 2
    draw.text((x, y), text, font=font, fill=fill)
    return y + (bbox[3] - bbox[1]) + 20


y = bell_y + bell_img.height + 50
y = draw_centered_text(draw, "ANTES DO SINO", y, font_bold, cream)
y = draw_centered_text(draw, "Teste com sino classico", y, font_regular, slate)

img.save("docs/test-bell.png")
print("Imagem de teste salva em docs/test-bell.png")
