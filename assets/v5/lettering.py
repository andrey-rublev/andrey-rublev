from io import BytesIO
from pathlib import Path

from PIL import ImageFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont


class HeroType:
    def __init__(self, font_path):
        self.font = TTFont(font_path)
        self.cmap = self.font.getBestCmap()
        self.units = self.font['head'].unitsPerEm
        self.display = self.font.getGlyphSet(location={'opsz': 96, 'wght': 800})
        self.caption = self.font.getGlyphSet(location={'opsz': 18, 'wght': 600})

    def outline(self, text, x, baseline, size, fill, *, display=False, spacing=0):
        glyphs = self.display if display else self.caption
        scale = size / self.units
        x /= scale
        paths = []
        for character in text:
            glyph = glyphs[self.cmap[ord(character)]]
            pen = SVGPathPen(glyphs, ntos=lambda value: str(round(value)))
            glyph.draw(pen)
            if commands := pen.getCommands():
                paths.append(f'    <path transform="translate({x:.2f})" d="{commands}"/>')
            x += glyph.width + spacing / scale

        group = f'<g fill="{fill}" transform="translate(0 {baseline}) scale({scale:.5f} {-scale:.5f})">'
        return '\n'.join((f'  {group}', *paths, '  </g>'))


FONT_PATH = Path(__file__).resolve().parent.parent / "v2" / "BricolageGrotesque.woff2"


class Typography:
    def __init__(self):
        self.faces = {}
        for name, axes in (
            ('display', {'wght': 750, 'opsz': 96, 'wdth': 100}),
            ('normal', {'wght': 550, 'opsz': 15, 'wdth': 100}),
            ('accent', {'wght': 680, 'opsz': 15, 'wdth': 100}),
        ):
            font = instantiateVariableFont(TTFont(FONT_PATH), axes)
            font.flavor = None
            data = BytesIO()
            font.save(data)
            self.faces[name] = data.getvalue()

    def font(self, name, size):
        return ImageFont.truetype(BytesIO(self.faces[name]), max(1, round(size)))
