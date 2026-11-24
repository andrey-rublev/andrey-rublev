"""Typography surrounding the deck. The printed playing cards use their own artwork."""
from base64 import b64encode
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parents[1] / "fonts"
# Match the surfaces and inks used by the original project cards.
COVER_PALETTES = {
    "light": {"surface": "#FFFFFF", "title": "#1F2328", "accent": "#5B4BD6",
              "rule": "#D0D7DE", "body": "#57606A", "shadow": "#434951"},
    "dark": {"surface": "#0D1117", "title": "#E6EDF3", "accent": "#818CF8",
             "rule": "#30363D", "body": "#8B949E", "shadow": "#000000"},
}


@lru_cache(maxsize=None)
def font_data(name):
    font = TTFont(FONTS / (name + ".subset.woff2"))
    font.flavor = None
    ttf = BytesIO()
    font.save(ttf)
    return ttf.getvalue()


@lru_cache(maxsize=64)
def typeface(name, size, weight=400):
    font = ImageFont.truetype(BytesIO(font_data(name)), size)
    if name == "PublicSans":
        font.set_variation_by_axes([weight])
    return font


@lru_cache(maxsize=None)
def embedded_faces():
    # Static weights also render reliably inside SVG images in WebKit.
    rules = []
    for family, weight in (("Newsreader", 460), ("PublicSans", 460), ("PublicSans", 600)):
        path = FONTS / (family + ".subset.woff2")
        if family == "PublicSans":
            face = instantiateVariableFont(TTFont(path, recalcTimestamp=False), {"wght": weight})
            output = BytesIO()
            face.save(output)
            data = output.getvalue()
        else:
            data = path.read_bytes()
        url = b64encode(data).decode("ascii")
        rules.append(f"@font-face{{font-family:{family};src:url(data:font/woff2;base64,{url}) format('woff2');font-weight:{weight}}}")
    return "".join(rules)


def draw_masthead(canvas, layout, scale, palette):
    pen = ImageDraw.Draw(canvas)
    def text(x, y, value, family, size, color=palette["title"], weight=400, tracking=0):
        font = typeface(family, round(size*scale), weight)
        px, py = round(x*scale), round(y*scale)
        if tracking:
            for char in value:
                pen.text((round(px), py), char, fill=color, font=font, anchor="ls")
                px += font.getlength(char) + tracking*scale
        else:
            pen.text((px, py), value, fill=color, font=font, anchor="ls")
        return x + font.getlength(value) / scale

    def rule(x1, x2, y):
        pen.line((round(x1*scale), round(y*scale), round(x2*scale), round(y*scale)),
                 fill=palette["rule"], width=max(1, round(scale*.65)))

    if layout == "mobile":
        text(18, 25, "COMPUTER ENGINEERING", "PublicSans", 10, weight=600, tracking=1.2)
        rule(190, 279, 21)
        text(291, 25, "PURDUE", "PublicSans", 10, weight=600, tracking=1.2)
        end = text(15, 84, "Nikhil", "Newsreader", 58)
        text(end + 11, 84, "Kolli", "Newsreader-Italic", 58, palette["accent"])
        return

    wide = layout == "wide"
    left, size, first, last = (32, 94, 146, 225) if wide else (20, 65, 110, 166)
    text(left, 34 if wide else 29, "PURDUE UNIVERSITY", "PublicSans",
         10.8 if wide else 9.2, weight=600, tracking=1.45 if wide else 1)
    rule(178 if wide else 141, 262 if wide else 162, 30 if wide else 25)
    text(left - 3, first, "Nikhil", "Newsreader", size)
    text(left + (24 if wide else 13), last, "Kolli", "Newsreader-Italic", size, palette["accent"])
    base = 281 if wide else 213
    rule(left, left + 27, base - 24)
    text(left, base, "Computer Engineering", "PublicSans", 16 if wide else 13, weight=600)
    text(left, base + 20, "Machine learning  /  Software", "PublicSans", 13 if wide else 11, palette["body"])
