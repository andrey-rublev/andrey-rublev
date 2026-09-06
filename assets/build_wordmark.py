"""
Builds the "NIKHIL KOLLI" wordmark in Bungee Shade + Bungee, two-tone 3D.

    python assets/build_wordmark.py

Why the font is embedded rather than named
------------------------------------------
GitHub serves README images through camo into an <img>. That context cannot
fetch external stylesheets or font files, so `font-family: 'Bungee Shade'` on
its own resolves to whatever the viewer happens to have installed - which for
almost everyone is nothing, and the mark silently falls back to a serif. The
font must travel inside the file, as a base64 data URI in an @font-face block.
That is the same technique readme-typing-svg uses, which is why the typing
banner in this README genuinely renders in JetBrains Mono.

Why two fonts
-------------
The Bungee family is built to be layered. Bungee Shade carries the 3D
extrusion, Bungee carries the solid face. Stacked in two colours and drawn at
identical coordinates, they give real two-tone depth; Bungee Shade alone is a
single flat colour.

A trap worth recording
----------------------
Google Fonts serves a separate file per unicode subset, and latin-ext is listed
*before* latin. Taking the first URL in the CSS yields a font containing no A-Z
at all - the browser then falls back and the mark looks nothing like the chosen
face, with no error anywhere. Pick the block whose unicode-range covers
U+0000-00FF, and assert the glyphs are present before trusting the file.

Regenerating the subsets needs `fonttools` and `brotli` plus network access;
rebuilding the SVGs from the committed subsets needs neither.
"""
import base64
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / "fonts"
FONTS.mkdir(exist_ok=True)

NAME = "NIKHIL KOLLI"
LETTERS = sorted(set(NAME.replace(" ", "")))

SIZE = 84
PAD_X = 40
PAD_Y = 26

# Bungee Shade sits under Bungee, at the same coordinates.
SHADE = ("Bungee_Shade", "Bungee Shade", "Bungee+Shade")
FACE = ("Bungee", "Bungee", "Bungee")

RISE_MS = 620
RISE_STAGGER = 46
SWEEP_PERIOD = 4800
SWEEP_BAND = 150

THEMES = {
    "dark": {"shade": "#6259E8", "face": "#F0F3F8", "sweep": "#FFFFFF", "sweep_op": 0.5},
    # On white the face has to be the dark element or it disappears.
    "light": {"shade": "#7C70E4", "face": "#16181D", "sweep": "#A5B4FC", "sweep_op": 0.45},
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _latin_url(spec: str) -> str:
    css = _fetch(f"https://fonts.googleapis.com/css2?family={spec}&display=swap").decode()
    for block in re.findall(r"@font-face\s*\{(.*?)\}", css, re.S):
        rng = re.search(r"unicode-range:([^;]+);", block)
        src = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", block)
        if src and rng and "U+0000-00FF" in rng.group(1):
            return src.group(1)
    raise RuntimeError(f"{spec}: no latin subset in the Google Fonts CSS")


def ensure_subset(slug: str, spec: str) -> pathlib.Path:
    """Committed subset if present, otherwise download the latin file and cut it."""
    sub = FONTS / f"{slug}.subset.woff2"
    if sub.exists():
        return sub

    from fontTools import subset
    from fontTools.ttLib import TTFont

    raw = FONTS / f"{slug}.woff2"
    if not raw.exists():
        raw.write_bytes(_fetch(_latin_url(spec)))

    cmap = TTFont(raw).getBestCmap()
    missing = [c for c in LETTERS if ord(c) not in cmap]
    if missing:
        raise RuntimeError(f"{slug}: latin subset is missing {missing}")

    opts = subset.Options()
    opts.flavor = "woff2"
    opts.desubroutinize = True
    font = subset.load_font(str(raw), opts)
    s = subset.Subsetter(options=opts)
    s.populate(text=NAME)
    s.subset(font)
    subset.save_font(font, str(sub), opts)
    font.close()
    return sub


def metrics(path: pathlib.Path):
    """Per-character x offsets and vertical metrics, from the font itself."""
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    scale = SIZE / upm

    xs, cursor = [], 0.0
    for ch in NAME:
        glyph = cmap.get(ord(ch)) or cmap.get(0x20)
        adv = hmtx[glyph][0] * scale if glyph else SIZE * 0.5
        xs.append((ch, cursor, adv))
        cursor += adv
    return {
        "chars": xs,
        "width": cursor,
        "asc": font["hhea"].ascent * scale,
        "desc": abs(font["hhea"].descent) * scale,
    }


def b64(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def render(theme: dict, shade_b64: str, face_b64: str, m: dict) -> str:
    vw = round(m["width"] + PAD_X * 2, 1)
    vh = round(m["asc"] + m["desc"] + PAD_Y * 2, 1)
    baseline = round(PAD_Y + m["asc"], 1)

    # One text element per character so each can rise on its own delay. Positions
    # come from the font's advances, so this matches a single run exactly.
    def run(cls: str) -> str:
        out = []
        i = 0
        for ch, x, _adv in m["chars"]:
            if ch == " ":
                continue
            out.append(
                f'<text class="{cls} c{i}" x="{round(PAD_X + x, 1)}" y="{baseline}">{ch}</text>'
            )
            i += 1
        return "".join(out)

    n = len([c for c, _, _ in m["chars"] if c != " "])
    stagger = "".join(f".c{i}{{animation-delay:{i * RISE_STAGGER}ms}}" for i in range(n))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" width="{vw}" height="{vh}" role="img" aria-label="{NAME}">
<title>{NAME}</title>
<defs>
  <clipPath id="band">
    <rect class="sweep" x="{-SWEEP_BAND}" y="0" width="{SWEEP_BAND}" height="{vh}"/>
  </clipPath>
</defs>
<style>
@font-face{{font-family:'BShade';src:url(data:font/woff2;base64,{shade_b64}) format('woff2');font-display:block}}
@font-face{{font-family:'BFace';src:url(data:font/woff2;base64,{face_b64}) format('woff2');font-display:block}}
text{{font-size:{SIZE}px;text-anchor:start}}
.sh{{font-family:'BShade',sans-serif;fill:{theme['shade']}}}
.fc{{font-family:'BFace',sans-serif;fill:{theme['face']}}}
.sw{{font-family:'BFace',sans-serif;fill:{theme['sweep']};opacity:{theme['sweep_op']}}}
text{{animation:rise {RISE_MS}ms cubic-bezier(.2,.85,.3,1) both}}
@keyframes rise{{from{{opacity:0;transform:translateY(15px)}}to{{opacity:1;transform:translateY(0)}}}}
{stagger}
/* The band moves, not the letters: translating the clipped group would carry
   its own clip along and nothing would appear to move. */
.sweep{{animation:sweep {SWEEP_PERIOD}ms linear infinite}}
@keyframes sweep{{0%{{transform:translateX(0)}}44%{{transform:translateX({round(vw + SWEEP_BAND, 1)}px)}}100%{{transform:translateX({round(vw + SWEEP_BAND, 1)}px)}}}}
</style>
{run('sh')}
{run('fc')}
<g clip-path="url(#band)">{run('sw')}</g>
</svg>
"""


def validate(svg: str, name: str) -> None:
    import xml.etree.ElementTree as ET

    ET.fromstring(svg)  # an unescaped < or & in the CSS is a silent broken image
    for token in ("@font-face", "base64,", "BShade", "BFace"):
        if token not in svg:
            raise RuntimeError(f"{name}: missing {token}")


def main() -> int:
    shade = ensure_subset(SHADE[0], SHADE[2])
    face = ensure_subset(FACE[0], FACE[2])
    m = metrics(shade)  # Shade and Bungee share metrics; the layers must align.

    sb, fb = b64(shade), b64(face)
    for theme_name, theme in THEMES.items():
        svg = render(theme, sb, fb, m)
        validate(svg, theme_name)
        out = HERE / f"wordmark-{theme_name}.svg"
        out.write_text(svg, encoding="utf-8")
        print(f"  wordmark-{theme_name}.svg  {len(svg) / 1024:.1f} KB")

    print(f"  subsets: {shade.stat().st_size}b shade + {face.stat().st_size}b face")
    print(f"  {round(m['width'] + PAD_X * 2)}x{round(m['asc'] + m['desc'] + PAD_Y * 2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
