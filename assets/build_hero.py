"""
Builds the header banner: the "NIKHIL KOLLI" wordmark over a typed tagline.

    python assets/build_hero.py

Writes hero-dark.svg and hero-light.svg for wide screens, and hero-m.svg for
phones - the same banner redrawn at 340 wide with the tagline broken onto three
lines, so it stays readable when the column is 300px across instead of 846.

Why the fonts are embedded rather than named
--------------------------------------------
GitHub serves README images through camo into an <img>. That context cannot
fetch external stylesheets or font files, so `font-family: 'Bungee Shade'` on
its own resolves to whatever the viewer happens to have installed - which for
almost everyone is nothing, and the mark silently falls back to a serif. The
font must travel inside the file, as a base64 data URI in an @font-face block.

The tagline used to come from readme-typing-svg, which does the same thing on
someone else's server. Drawing it here means it shares the banner, cannot go
down with that service, and can break onto three lines on a phone instead of
shrinking to 8px.

Why two fonts for the name
--------------------------
The Bungee family is built to be layered. Bungee Shade carries the 3D
extrusion, Bungee carries the solid face. Stacked in two colours and drawn at
identical coordinates, they give real two-tone depth; Bungee Shade alone is a
single flat colour.

How the typing works
--------------------
Each line sits under a clip band that slides right in steps(n) - one step per
character, which is exact because JetBrains Mono advances every glyph the same
width. The caret rides the same steps. A band's resting position is fully
open, and only the animation starts it closed, so anything that does not run
the animation still shows the whole line.

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
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
FONTS = HERE / "fonts"
FONTS.mkdir(exist_ok=True)

NAME = "NIKHIL KOLLI"
TAGLINE = ["RL/ML/AI, SWE, ECE", "CompE @ Purdue", "nikhilkolli.com"]
SEP = " | "

# (file slug, Google Fonts family spec, the text it has to cover)
SHADE = ("Bungee_Shade", "Bungee+Shade", NAME)
FACE = ("Bungee", "Bungee", NAME)
MONO = ("JetBrains_Mono_600", "JetBrains+Mono:wght@600", SEP.join(TAGLINE))

# Wide banner: fills the README column, which tops out at 846px.
W, H = 846, 196
NAME_SIZE = 60
NAME_Y = 94         # baseline
TAG_SIZE = 18
TAG_Y = 146

# Phone banner: drawn at 340 and scaled to the column.
MW, MH = 340, 190
M_NAME_SIZE = 30
M_NAME_Y = 62
M_TAG_SIZE = 14
M_TAG_Y, M_TAG_LEAD = 104, 22

RISE_MS = 620
RISE_STAGGER = 46
SWEEP_PERIOD = 4800
SWEEP_BAND = 150
TYPE_DELAY = 1.05   # s - after the last letter of the name has landed
TYPE_CPS = 24       # characters per second
BLINK = 1.06        # s

THEMES = {
    "dark": {
        "bg0": "#111827", "bg1": "#0D1117", "border": "#262C36",
        "dots": "#E6EDF3", "dots_op": 0.10, "glow": "#6366F1", "glow_op": 0.36,
        "marks": "#3D444D",
        # The sweep is the face colour inverted, which clears the face by the
        # widest margin there is - an earlier white-on-near-white sweep was
        # running correctly and completely invisible, at 1.05:1.
        "shade": "#6259E8", "face": "#F0F3F8", "sweep": "#0F0C07", "sweep_op": 0.8,
        "tag": "#A5B4FC", "sep": "#484F58", "caret": "#818CF8",
    },
    "light": {
        "bg0": "#F3F4FF", "bg1": "#FFFFFF", "border": "#D0D7DE",
        "dots": "#1F2328", "dots_op": 0.10, "glow": "#818CF8", "glow_op": 0.26,
        "marks": "#C4CBD3",
        # On white the face has to be the dark element or it disappears.
        "shade": "#7C70E4", "face": "#16181D", "sweep": "#E9E7E2", "sweep_op": 0.8,
        "tag": "#4F46E5", "sep": "#AFB8C1", "caret": "#5B4BD6",
    },
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


def _covers(path: pathlib.Path, text: str) -> bool:
    from fontTools.ttLib import TTFont

    cmap = TTFont(path).getBestCmap()
    return all(ord(c) in cmap for c in set(text))


def ensure_subset(slug: str, spec: str, text: str, name: str = "") -> pathlib.Path:
    """Committed subset if it covers the text, otherwise cut a fresh one.

    `name` lets two images cut separate subsets from one downloaded face, so
    neither has to carry the other's glyphs.
    """
    sub = FONTS / f"{name or slug}.subset.woff2"
    if sub.exists() and _covers(sub, text):
        return sub

    from fontTools import subset

    raw = FONTS / f"{slug}.woff2"
    if not raw.exists():
        raw.write_bytes(_fetch(_latin_url(spec)))
    if not _covers(raw, text):
        raise RuntimeError(f"{slug}: latin file is missing glyphs for {text!r}")

    opts = subset.Options()
    opts.flavor = "woff2"
    opts.desubroutinize = True
    font = subset.load_font(str(raw), opts)
    s = subset.Subsetter(options=opts)
    s.populate(text=text)
    s.subset(font)
    subset.save_font(font, str(sub), opts)
    font.close()
    return sub


def advances(path: pathlib.Path, text: str) -> list:
    """Advance of each character of text, in ems."""
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    return [font["hmtx"][cmap[ord(c)]][0] / upm for c in text]


def ink(path: pathlib.Path, ch: str) -> tuple:
    """(left, right) of a glyph's ink, in ems."""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[font.getBestCmap()[ord(ch)]].draw(pen)
    upm = font["head"].unitsPerEm
    return pen.bounds[0] / upm, pen.bounds[2] / upm


def b64(path: pathlib.Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


class Fonts:
    def __init__(self):
        self.shade = ensure_subset(*SHADE)
        self.face = ensure_subset(*FACE)
        self.mono = ensure_subset(*MONO)
        # Shade and Bungee share metrics; the layers must align, so both are
        # placed on Shade's advances.
        self.name_adv = advances(self.shade, NAME)
        self.name_ink = (ink(self.shade, NAME[0])[0],
                         sum(self.name_adv[:-1]) + ink(self.shade, NAME[-1])[1])
        self.mono_adv = advances(self.mono, "M")[0]

    def css(self) -> str:
        return (f"@font-face{{font-family:'BShade';src:url(data:font/woff2;base64,{b64(self.shade)}) format('woff2');font-display:block}}\n"
                f"@font-face{{font-family:'BFace';src:url(data:font/woff2;base64,{b64(self.face)}) format('woff2');font-display:block}}\n"
                f"@font-face{{font-family:'JBMono';src:url(data:font/woff2;base64,{b64(self.mono)}) format('woff2');font-display:block}}\n")


def wordmark(f: Fonts, cx: float, baseline: float, size: float, clip: str) -> str:
    """The name as three stacked runs - shade, face, sweep - centred on its ink."""
    left = cx - (f.name_ink[0] + f.name_ink[1]) / 2 * size
    letters, x = [], left
    for ch, adv in zip(NAME, f.name_adv):
        if ch != " ":
            letters.append((ch, round(x, 1)))
        x += adv * size

    def run(cls: str) -> str:
        return "".join(f'<text class="{cls} c{i}" x="{x}" y="{baseline}">{ch}</text>'
                       for i, (ch, x) in enumerate(letters))

    return (f'<g font-size="{size}">'
            f"{run('sh')}{run('fc')}"
            f'<g clip-path="url(#{clip})">{run("sw")}</g></g>')


def typed(lines: list, f: Fonts, cx: float, y0: float, lead: float, size: float,
          ids: str) -> tuple:
    """Lines of mono text that type themselves out, one after another.

    `lines` is a list of runs: [(text, class), ...] per line. Returns the
    markup and the CSS that drives it.
    """
    cw = f.mono_adv * size
    out, css = [], []
    t = TYPE_DELAY
    for i, runs in enumerate(lines):
        text = "".join(s for s, _ in runs)
        n, width = len(text), len(text) * cw
        x0 = round(cx - width / 2, 2)
        y = y0 + i * lead
        dur = round(n / TYPE_CPS, 3)
        last = i == len(lines) - 1

        spans = "".join(f'<tspan class="{c}">{esc(s)}</tspan>' for s, c in runs)
        band = f"{ids}b{i}"
        out.append(
            f'<clipPath id="{band}"><rect class="{band}" x="{x0 - width:.2f}" y="{y - size * 1.1:.2f}" '
            f'width="{width:.2f}" height="{size * 1.5:.2f}"/></clipPath>'
            f'<text class="mono" x="{x0}" y="{y}" font-size="{size}" clip-path="url(#{band})">{spans}</text>'
        )
        # The band rests fully open; only the animation starts it shut.
        css.append(f".{band}{{transform:translateX({width:.2f}px);animation:{band} {dur}s steps({n},end) {t:.3f}s both}}"
                   f"@keyframes {band}{{from{{transform:translateX(0)}}}}")

        # Carets: each one appears with its line, and only the last one stays
        # to blink. The block sits on the mono cap height. The first waits at
        # the start of its line, already showing; later ones hide until theirs.
        caret = f"{ids}k{i}"
        rect = (f'<rect class="caret {caret}" x="{x0:.2f}" y="{y - size * 0.78:.2f}" '
                f'width="{cw * 0.62:.2f}" height="{size * 0.92:.2f}" rx="1"/>')
        anims = [f"{band} {dur}s steps({n},end) {t:.3f}s both"]
        if i:
            anims.append(f"pre 1ms step-end {t:.3f}s backwards")
        if last:
            # The blink lives on a wrapper so reduced motion can stop it alone.
            blink = f"{ids}bl"
            rect = f'<g class="blink {blink}">{rect}</g>'
            css.append(f".{blink}{{animation:blink {BLINK}s step-end {t + dur:.3f}s infinite}}")
        else:
            anims.append(f"post 1ms step-end {t + dur + 0.25:.3f}s forwards")
        out.append(rect)
        # Resting state: at the end of its line.
        css.append(f".{caret}{{transform:translateX({width:.2f}px);animation:{', '.join(anims)}}}")
        t += dur + 0.35
    return "".join(out), "".join(css)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def backdrop(w: float, h: float, ids: str, name_y: float) -> str:
    """Panel, dot grid fading out from the centre, a glow behind the name, and
    crop marks in the corners."""
    m, tick = 14, 9
    corners = "".join(
        f'<path class="marks" d="M{x} {y + dy * tick}V{y}H{x + dx * tick}"/>'
        for x, y, dx, dy in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1))
    )
    return (
        f'<defs>'
        f'<linearGradient id="{ids}bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" class="bg0"/><stop offset="1" class="bg1"/></linearGradient>'
        f'<pattern id="{ids}dots" width="18" height="18" patternUnits="userSpaceOnUse">'
        f'<circle class="dots" cx="9" cy="9" r="1"/></pattern>'
        f'<radialGradient id="{ids}fade" cx="50%" cy="45%" r="62%">'
        f'<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="{ids}vignette"><rect width="{w}" height="{h}" fill="url(#{ids}fade)"/></mask>'
        f'<radialGradient id="{ids}glow"><stop offset="0" class="glow"/><stop offset="1" class="glow-end"/></radialGradient>'
        f'<clipPath id="{ids}panel"><rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14"/></clipPath>'
        f'</defs>'
        f'<g clip-path="url(#{ids}panel)">'
        f'<rect width="{w}" height="{h}" fill="url(#{ids}bg)"/>'
        f'<rect width="{w}" height="{h}" fill="url(#{ids}dots)" mask="url(#{ids}vignette)"/>'
        f'<ellipse cx="{w / 2}" cy="{name_y - 18}" rx="{w * 0.36:.1f}" ry="{h * 0.42:.1f}" fill="url(#{ids}glow)"/>'
        f'</g>'
        f'<rect class="frame" x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="14" fill="none"/>'
        + corners
    )


def theme_css(t: dict, scope: str = "") -> str:
    p = f".{scope} " if scope else ""
    return (f"{p}.bg0{{stop-color:{t['bg0']}}}{p}.bg1{{stop-color:{t['bg1']}}}"
            f"{p}.dots{{fill:{t['dots']};fill-opacity:{t['dots_op']}}}"
            f"{p}.glow{{stop-color:{t['glow']};stop-opacity:{t['glow_op']}}}"
            f"{p}.glow-end{{stop-color:{t['glow']};stop-opacity:0}}"
            f"{p}.frame{{stroke:{t['border']}}}{p}.marks{{fill:none;stroke:{t['marks']};stroke-width:1.25}}"
            f"{p}.sh{{fill:{t['shade']}}}{p}.fc{{fill:{t['face']}}}"
            f"{p}.sw{{fill:{t['sweep']};opacity:{t['sweep_op']}}}"
            f"{p}.tg{{fill:{t['tag']}}}{p}.sp{{fill:{t['sep']}}}{p}.caret{{fill:{t['caret']};opacity:.85}}\n")


def base_css(n_letters: int, sweep_to: float) -> str:
    stagger = "".join(f".c{i}{{animation-delay:{i * RISE_STAGGER}ms}}" for i in range(n_letters))
    return (
        ".sh{font-family:'BShade',sans-serif}.fc,.sw{font-family:'BFace',sans-serif}\n"
        ".mono{font-family:'JBMono',ui-monospace,monospace;font-weight:600;white-space:pre}\n"
        f".sh,.fc,.sw{{animation:rise {RISE_MS}ms cubic-bezier(.2,.85,.3,1) both}}\n"
        "@keyframes rise{from{opacity:0;transform:translateY(15px)}to{opacity:1;transform:translateY(0)}}\n"
        f"{stagger}\n"
        # The band moves, not the letters: translating the clipped group would
        # carry its own clip along and nothing would appear to move.
        f".sweep{{animation:sweep {SWEEP_PERIOD}ms linear infinite}}\n"
        f"@keyframes sweep{{0%{{transform:translateX(0)}}44%,100%{{transform:translateX({sweep_to:.1f}px)}}}}\n"
        "@keyframes pre{from,to{opacity:0}}@keyframes post{from,to{opacity:0}}\n"
        "@keyframes blink{50%{opacity:0}}\n"
        # Reduced motion drops what moves - the letters rising, the sweep, the
        # blink - and keeps what only appears: the name fades in and the
        # tagline still types. Turning everything off was the first version,
        # and it froze the banner for anyone with Windows' "Animation effects"
        # switched off, which Chrome reports to images as reduced motion.
        "@keyframes fade{from{opacity:0}}\n"
        "@media (prefers-reduced-motion: reduce){.sh,.fc,.sw{animation-name:fade}"
        ".sweep,.blink{animation:none!important}}\n"
    )


def sweep_band(ids: str, h: float) -> str:
    return (f'<clipPath id="{ids}band"><rect class="sweep" x="{-SWEEP_BAND}" y="0" '
            f'width="{SWEEP_BAND}" height="{h}"/></clipPath>')


def doc(w: float, h: float, label: str, css: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{label}">\n<title>{label}</title>\n'
            f"<style>\n{css}</style>\n{body}\n</svg>\n")


LABEL = f"{NAME.title()} - {SEP.join(TAGLINE)}"


def wide(f: Fonts, t: dict) -> str:
    runs = []
    for i, part in enumerate(TAGLINE):
        if i:
            runs.append((SEP, "sp"))
        runs.append((part, "tg"))
    text, text_css = typed([runs], f, W / 2, TAG_Y, 0, TAG_SIZE, "w")
    body = (backdrop(W, H, "w", NAME_Y)
            + f"<defs>{sweep_band('w', H)}</defs>"
            + wordmark(f, W / 2, NAME_Y, NAME_SIZE, "wband")
            + text)
    css = f.css() + base_css(len(NAME.replace(" ", "")), W + SWEEP_BAND) + theme_css(t) + text_css + "\n"
    return doc(W, H, LABEL, css, body)


def narrow(f: Fonts) -> str:
    """Both themes in one file, picked by prefers-color-scheme inside the SVG.

    A phone-width <source> must not mention prefers-color-scheme: for anyone
    with an explicit GitHub theme, GitHub's themed-picture script rewrites the
    media of every such source and throws the width condition away - see
    build_project_cards.adaptive_card.
    """
    lines = [[(part, "tg")] for part in TAGLINE]
    layers, css = [], [f.css(), base_css(len(NAME.replace(" ", "")), MW + SWEEP_BAND)]
    for name, t in THEMES.items():
        ids = f"m{name[0]}"
        text, text_css = typed(lines, f, MW / 2, M_TAG_Y, M_TAG_LEAD, M_TAG_SIZE, ids)
        layers.append(f'<g class="{name}">'
                      + backdrop(MW, MH, ids, M_NAME_Y)
                      + f"<defs>{sweep_band(ids, MH)}</defs>"
                      + wordmark(f, MW / 2, M_NAME_Y, M_NAME_SIZE, f"{ids}band")
                      + text + "</g>")
        css += [theme_css(t, name), text_css + "\n"]
    css.append(".light{display:none}\n"
               "@media (prefers-color-scheme: light){.dark{display:none}.light{display:inline}}\n")
    return doc(MW, MH, LABEL, "".join(css), "".join(layers))


def validate(svg: str, name: str) -> None:
    ET.fromstring(svg)  # an unescaped < or & in the CSS is a silent broken image
    for token in ("@font-face", "base64,", "BShade", "BFace", "JBMono"):
        if token not in svg:
            raise RuntimeError(f"{name}: missing {token}")


def main() -> int:
    f = Fonts()
    out = {f"hero-{name}.svg": wide(f, t) for name, t in THEMES.items()}
    out["hero-m.svg"] = narrow(f)
    for name, svg in out.items():
        validate(svg, name)
        (HERE / name).write_text(svg, encoding="utf-8")
        print(f"  {name:<16} {len(svg) / 1024:.1f} KB")
    print(f"  subsets: {', '.join(f'{p.name} {p.stat().st_size}b' for p in (f.shade, f.face, f.mono))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
