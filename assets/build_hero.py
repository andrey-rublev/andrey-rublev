"""
Builds the header banner: the name on an IC package, wired into a circuit board.

    python assets/build_hero.py

The README is drawn as a board - this is a computer engineer's profile - and
the banner is where that starts. "NIKHIL KOLLI" is the label on a chip, the
tagline is its part marking, typed out once the chip powers up, and traces fan
out from the pins across a perfboard to vias and off the edge of the board.
Every few seconds a pulse of light runs along a trace into the chip, and the
pin it lands on flashes.

Writes hero-dark.svg and hero-light.svg for wide screens, and hero-m.svg for
phones - the same board redrawn at 340 wide with the marking on three lines,
so it stays readable when the column is 300px across instead of 846.

Why the fonts are embedded rather than named
--------------------------------------------
GitHub serves README images through camo into an <img>. That context cannot
fetch external stylesheets or font files, so `font-family: 'Bungee Shade'` on
its own resolves to whatever the viewer happens to have installed - which for
almost everyone is nothing, and the mark silently falls back to a serif. The
font must travel inside the file, as a base64 data URI in an @font-face block.

Why two fonts for the name
--------------------------
The Bungee family is built to be layered. Bungee Shade carries the 3D
extrusion, Bungee carries the solid face. Stacked in two colours and drawn at
identical coordinates, they give real two-tone depth; Bungee Shade alone is a
single flat colour.

How the motion works
--------------------
Traces are polylines of straight runs and 45-degree bends, so their lengths
are exact and every dash pattern can be computed rather than guessed. A trace
draws itself in by sliding a dash the length of the path; a pulse is a short
dash sliding from the far end to the pin over a fixed period, staggered so a
few are in flight at once.

The marking types under a clip band that slides right in steps(n) - one step
per character, exact because JetBrains Mono advances every glyph the same
width. Every resting state is the finished picture - traces drawn, band open,
pulses parked past the end of their trace - so anything that does not run the
animation still shows the whole board.

Reduced motion keeps what only appears (the fade-ins, the typing) and drops
what travels: the letters rising, the traces drawing, the pulses. Chrome
reports Windows' "Animation effects" switch to images as reduced motion, so
this is what a lot of desktop viewers get.

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
import math
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

# Timeline, in seconds from load.
CHIP_IN = 0.35
NAME_IN = 0.55
RISE_MS, RISE_STAGGER = 620, 46
TYPE_AT = 1.45
TYPE_CPS = 26
PULSES_AT = 2.4
PERIOD = 8.0        # each trace fires once per period
SPEED = 170         # px/s along a trace

THEMES = {
    "dark": {
        "sub0": "#0F1422", "sub1": "#0D1117", "border": "#262C36",
        "dots": "#E6EDF3", "dots-op": ".07", "halo": "#6366F1", "halo-op": ".26",
        "trace": "#283050", "via": "#3A4466", "pulse": "#E0E7FF", "glow": "#818CF8",
        "chip0": "#1B2134", "chip1": "#111624", "chipbd": "#333C5A", "chiphi": "#56618C",
        "pin": "#4A5475", "pin1": "#3A4466", "hot": "#C7D2FE",
        "shade": "#6259E8", "face": "#F0F3F8", "tag": "#A5B4FC", "sep": "#4B5470", "caret": "#818CF8",
    },
    "light": {
        "sub0": "#F3F4FE", "sub1": "#FFFFFF", "border": "#D0D7DE",
        "dots": "#1F2328", "dots-op": ".09", "halo": "#818CF8", "halo-op": ".20",
        "trace": "#D5D9F3", "via": "#B7BDE5", "pulse": "#4F46E5", "glow": "#A5B4FC",
        "chip0": "#FFFFFF", "chip1": "#F1F2F9", "chipbd": "#C3C9E2", "chiphi": "#FFFFFF",
        "pin": "#A9B0D0", "pin1": "#D5D9F3", "hot": "#4F46E5",
        "shade": "#7C70E4", "face": "#16181D", "tag": "#4F46E5", "sep": "#AFB8C1", "caret": "#5B4BD6",
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


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wordmark(f: Fonts, cx: float, baseline: float, size: float) -> str:
    """The name as two stacked runs - shade under face - centred on its ink."""
    left = cx - (f.name_ink[0] + f.name_ink[1]) / 2 * size
    letters, x = [], left
    for ch, adv in zip(NAME, f.name_adv):
        if ch != " ":
            letters.append((ch, round(x, 1)))
        x += adv * size

    def run(cls: str) -> str:
        return "".join(f'<text class="{cls} c{i}" x="{x}" y="{baseline}">{ch}</text>'
                       for i, (ch, x) in enumerate(letters))

    return f'<g font-size="{size}">{run("sh")}{run("fc")}</g>'


def typed(lines: list, f: Fonts, cx: float, y0: float, lead: float, size: float) -> tuple:
    """Lines of mono text that type themselves out, one after another.

    `lines` holds a list of (text, class) runs per line. Returns markup and CSS.
    """
    cw = f.mono_adv * size
    out, css = [], []
    t = TYPE_AT
    for i, runs in enumerate(lines):
        text = "".join(s for s, _ in runs)
        n, width = len(text), len(text) * cw
        x0 = round(cx - width / 2, 2)
        y = y0 + i * lead
        dur = round(n / TYPE_CPS, 3)
        spans = "".join(f'<tspan class="{c}">{esc(s)}</tspan>' for s, c in runs)
        out.append(
            f'<clipPath id="b{i}"><rect class="b{i}" x="{x0 - width:.2f}" y="{y - size * 1.1:.2f}" '
            f'width="{width:.2f}" height="{size * 1.5:.2f}"/></clipPath>'
            f'<text class="mono" x="{x0}" y="{y}" font-size="{size}" clip-path="url(#b{i})">{spans}</text>'
            f'<rect class="caret k{i}" x="{x0:.2f}" y="{y - size * 0.78:.2f}" '
            f'width="{cw * 0.62:.2f}" height="{size * 0.92:.2f}" rx="1"/>')
        # The band rests fully open; only the animation starts it shut. The
        # caret rides the same steps and shows only while its line types.
        steps = f"{dur}s steps({n},end) {t:.3f}s both"
        css.append(f".b{i}{{transform:translateX({width:.2f}px);animation:b{i} {steps}}}"
                   f"@keyframes b{i}{{from{{transform:translateX(0)}}}}"
                   f".k{i}{{transform:translateX({width:.2f}px);opacity:0;"
                   f"animation:b{i} {steps},on {dur + 0.3:.3f}s step-end {t:.3f}s}}")
        t += dur + 0.3
    return "".join(out), "".join(css)


# ---------------------------------------------------------------- the board

class Board:
    """Chip geometry plus the traces wired to its pins."""

    def __init__(self, w, h, chip, pitch, pins, pin, side_pins, side_pin, chamfer, pulse):
        self.w, self.h = w, h
        self.cx, self.cy, self.cw, self.ch = chip
        self.pitch, self.pins, self.pin = pitch, pins, pin
        self.side_pins, self.side_pin = side_pins, side_pin
        self.c, self.pulse = chamfer, pulse
        self.top = self.cy - pin[1]                 # y of a top pin's tip
        self.bottom = self.cy + self.ch + pin[1]
        self.left = self.cx - side_pin[0]
        self.right = self.cx + self.cw + side_pin[0]
        self.traces = []                            # (points via-first, has_via)

    def off(self, hdir=0, vdir=0):
        """A coordinate just past the board's edge."""
        if hdir:
            return -12 if hdir < 0 else self.w + 12
        return -12 if vdir < 0 else self.h + 12

    def bus(self, pins, vdir, hdir, gap, step, ends):
        """Parallel traces leaving one edge, turning together through 45 degrees.

        `pins` runs outermost first: the outermost turns closest to the chip,
        so each inner trace passes clear over the ones outside it. An end of
        None runs the trace off the board.
        """
        tip, c = (self.top if vdir < 0 else self.bottom), self.c
        for k, (x, end) in enumerate(zip(pins, ends)):
            y = tip + vdir * (gap + k * step)
            ex = end if end is not None else self.off(hdir=hdir)
            self.traces.append(([(ex, y), (x + hdir * c, y), (x, y - vdir * c), (x, tip)], end is not None))

    def stub(self, x, vdir, end):
        tip = self.top if vdir < 0 else self.bottom
        ey = end if end is not None else self.off(vdir=vdir)
        self.traces.append(([(x, ey), (x, tip)], end is not None))

    def side(self, y, hdir, end):
        tip = self.left if hdir < 0 else self.right
        ex = end if end is not None else self.off(hdir=hdir)
        self.traces.append(([(ex, y), (tip, y)], end is not None))

    def pin_rects(self):
        (pw, ph), (sw, sh) = self.pin, self.side_pin
        for x in self.pins:
            yield (x - pw / 2, self.top, pw, ph)
            yield (x - pw / 2, self.cy + self.ch, pw, ph)
        for y in self.side_pins:
            yield (self.left, y - sh / 2, sw, sh)
            yield (self.cx + self.cw, y - sh / 2, sw, sh)

    def pin_at(self, point):
        """The pin rect a trace lands on."""
        x, y = point
        for r in self.pin_rects():
            rx, ry, rw, rh = r
            if rx - 0.1 <= x <= rx + rw + 0.1 and ry - 0.1 <= y <= ry + rh + 0.1:
                return r
        raise ValueError(f"no pin at {point}")


def length(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def path(pts) -> str:
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in pts)


def board_markup(b: Board, holes: bool) -> tuple:
    """Everything but the lettering: substrate, traces, pulses and the chip."""
    w, h = b.w, b.h
    css = []
    traces, vias, pulses, hots = [], [], [], []
    for i, (pts, via) in enumerate(b.traces):
        d, n = path(pts), length(pts)
        # Draw-in: a dash the length of the trace slides in from the pin end.
        lag = 0.05 + 0.025 * i
        traces.append(f'<path class="tr" d="{d}" style="stroke-dasharray:{n + 1:.1f} {n + 1:.1f};'
                      f'animation:d{i} .9s cubic-bezier(.3,.7,.2,1) {lag:.3f}s both"/>')
        css.append(f"@keyframes d{i}{{from{{stroke-dashoffset:{-(n + 1):.1f}}}}}")
        if via:
            vx, vy = pts[0]
            vias.append(f'<circle class="via" cx="{vx:g}" cy="{vy:g}" r="{3.4 if w > 400 else 2.8}" '
                        f'style="animation-delay:{lag + 0.55:.3f}s"/>')

        # Pulse: a short dash from the far end to the pin, once per period.
        # Delays step round the board by the golden ratio, so they never bunch.
        delay = PULSES_AT + (i * 0.6180339887 % 1) * PERIOD
        q = min(n / SPEED / PERIOD * 100, 40)
        D = b.pulse
        css.append(f"@keyframes p{i}{{0%{{stroke-dashoffset:{D + 4}}}{q:.2f}%,100%{{stroke-dashoffset:{-(n + 4):.1f}}}}}"
                   f"@keyframes h{i}{{0%,{max(q - 1, 0):.2f}%{{opacity:0}}{q:.2f}%{{opacity:1}}{q + 6:.2f}%,100%{{opacity:0}}}}")
        anim = f"p{i} {PERIOD}s cubic-bezier(.5,0,.6,1) {delay:.3f}s infinite both"
        for cls in ("pg", "pc"):
            pulses.append(f'<path class="{cls}" d="{d}" style="stroke-dasharray:{D} {n + D + 20:.1f};animation:{anim}"/>')
        rx, ry, rw, rh = b.pin_at(pts[-1])
        hots.append(f'<rect class="hot" x="{rx:g}" y="{ry:g}" width="{rw:g}" height="{rh:g}" rx="1" '
                    f'style="animation:h{i} {PERIOD}s linear {delay:.3f}s infinite both"/>')

    pins = "".join(f'<rect class="pin" x="{x:g}" y="{y:g}" width="{pw:g}" height="{ph:g}" rx="1"/>'
                   for x, y, pw, ph in b.pin_rects())
    x, y, cw, ch = b.cx, b.cy, b.cw, b.ch
    r = 10 if w > 400 else 8
    dot = (x + 16, y + 16, 4) if w > 400 else (x + 12, y + 12, 3)
    chip = (
        f'<g class="chip">{pins}'
        f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}" rx="{r}" fill="url(#chipg)"/>'
        f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="{r - 1}" fill="none" stroke="url(#chiphl)"/>'
        f'<rect class="chipbd" x="{x + 0.5}" y="{y + 0.5}" width="{cw - 1}" height="{ch - 1}" rx="{r}" fill="none"/>'
        f'<path class="notch" d="M{x + 0.5} {y + ch / 2 - 7}a7 7 0 0 1 0 14"/>'
        f'<circle class="pin1" cx="{dot[0]}" cy="{dot[1]}" r="{dot[2]}"/>'
        f'</g>')

    mounts = ""
    if holes:
        mounts = "".join(f'<circle class="hole" cx="{hx}" cy="{hy}" r="5"/><circle class="holec" cx="{hx}" cy="{hy}" r="2"/>'
                         for hx in (16, w - 16) for hy in (16, h - 16))

    rx = 14 if w > 400 else 12
    defs = (
        '<defs>'
        '<linearGradient id="sub" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" style="stop-color:var(--sub0)"/><stop offset="1" style="stop-color:var(--sub1)"/></linearGradient>'
        '<pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse">'
        '<circle class="dot" cx="8" cy="8" r="1"/></pattern>'
        '<radialGradient id="fade" cx="50%" cy="50%" r="65%">'
        '<stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="vignette"><rect width="{w}" height="{h}" fill="url(#fade)"/></mask>'
        '<radialGradient id="halo"><stop offset="0" style="stop-color:var(--halo);stop-opacity:var(--halo-op)"/>'
        '<stop offset="1" style="stop-color:var(--halo);stop-opacity:0"/></radialGradient>'
        '<linearGradient id="chipg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" style="stop-color:var(--chip0)"/><stop offset="1" style="stop-color:var(--chip1)"/></linearGradient>'
        '<linearGradient id="chiphl" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" style="stop-color:var(--chiphi);stop-opacity:.9"/><stop offset=".35" style="stop-color:var(--chiphi);stop-opacity:0"/></linearGradient>'
        f'<clipPath id="panel"><rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}"/></clipPath>'
        '</defs>')
    body = (
        defs
        + '<g clip-path="url(#panel)">'
        + f'<rect width="{w}" height="{h}" fill="url(#sub)"/>'
        + f'<rect width="{w}" height="{h}" fill="url(#dots)" mask="url(#vignette)"/>'
        + f'<ellipse cx="{x + cw / 2}" cy="{y + ch / 2}" rx="{cw * 0.75:.0f}" ry="{ch * 1.1:.0f}" fill="url(#halo)"/>'
        + mounts + "".join(traces) + "".join(vias) + "".join(pulses) + chip + "".join(hots)
        + '</g>'
        + f'<rect class="frame" x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}"/>')
    return body, "".join(css)


def variables(t: dict) -> str:
    return "svg{" + ";".join(f"--{k}:{v}" for k, v in t.items()) + "}"


def base_css(n_letters: int, w: float) -> str:
    stagger = "".join(f".c{i}{{animation-delay:{NAME_IN + i * RISE_STAGGER / 1000:.3f}s}}" for i in range(n_letters))
    thin = 1.5 if w > 400 else 1.2
    return (
        ".frame{fill:none;stroke:var(--border)}.dot{fill:var(--dots);fill-opacity:var(--dots-op)}\n"
        f".tr{{fill:none;stroke:var(--trace);stroke-width:{thin};stroke-linejoin:round}}\n"
        f".via{{fill:var(--sub1);stroke:var(--via);stroke-width:{thin};animation:fade .35s ease both}}\n"
        f".pg{{fill:none;stroke:var(--glow);stroke-opacity:.35;stroke-width:{thin * 4};stroke-linecap:round}}\n"
        f".pc{{fill:none;stroke:var(--pulse);stroke-width:{thin * 1.15};stroke-linecap:round}}\n"
        ".pin{fill:var(--pin)}.hot{fill:var(--hot);opacity:0}\n"
        ".chipbd{stroke:var(--chipbd)}.notch{fill:var(--sub1);stroke:var(--chipbd)}.pin1{fill:var(--pin1)}\n"
        ".hole{fill:none;stroke:var(--via);stroke-width:1.5}.holec{fill:var(--trace)}\n"
        ".sh{font-family:'BShade',sans-serif;fill:var(--shade)}.fc{font-family:'BFace',sans-serif;fill:var(--face)}\n"
        ".mono{font-family:'JBMono',ui-monospace,monospace;font-weight:600;white-space:pre}\n"
        ".tg{fill:var(--tag)}.sp{fill:var(--sep)}.caret{fill:var(--caret)}\n"
        f".chip{{animation:chipin .7s cubic-bezier(.2,.85,.3,1) {CHIP_IN}s both}}\n"
        f".sh,.fc{{animation:rise {RISE_MS}ms cubic-bezier(.2,.85,.3,1) both}}\n"
        f"{stagger}\n"
        "@keyframes chipin{from{opacity:0;transform:translateY(8px)}}\n"
        "@keyframes rise{from{opacity:0;transform:translateY(15px)}}\n"
        "@keyframes fade{from{opacity:0}}@keyframes on{from,to{opacity:1}}\n"
        # Reduced motion keeps what only appears and drops what travels.
        "@media (prefers-reduced-motion: reduce){.chip,.sh,.fc{animation-name:fade}"
        ".tr{animation:none!important}.pg,.pc,.hot{display:none}}\n"
    )


def doc(w: float, h: float, label: str, css: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{label}">\n<title>{label}</title>\n'
            f"<style>\n{css}</style>\n{body}\n</svg>\n")


LABEL = f"{NAME.title()} - {SEP.join(TAGLINE)}"


def wide_board() -> Board:
    w = 846
    b = Board(w, 254, (123, 62, 600, 130), 20, [143 + 20 * k for k in range(29)], (8, 9),
              [87, 107, 127, 147, 167], (9, 8), chamfer=6, pulse=18)
    # Top: a bus of four at each corner, a pair mid-way along, three up the middle.
    b.bus([143, 163, 183, 203], -1, -1, 9, 10, [70, 50, None, 30])
    b.bus([703, 683, 663, 643], -1, +1, 9, 10, [w - 70, w - 50, None, w - 30])
    b.bus([263, 283], -1, -1, 9, 10, [238, 226])
    b.bus([583, 563], -1, +1, 9, 10, [w - 238, w - 226])
    b.stub(383, -1, 24); b.stub(423, -1, None); b.stub(463, -1, 24)
    # Bottom: the same idea, varied so the board does not read as a mirror.
    b.bus([143, 163, 183], +1, -1, 9, 10, [64, None, 36])
    b.bus([703, 683, 663], +1, +1, 9, 10, [w - 64, None, w - 36])
    b.bus([303, 323, 343], +1, -1, 9, 10, [278, 262, 246])
    b.bus([543, 523, 503], +1, +1, 9, 10, [w - 278, w - 262, w - 246])
    b.stub(403, +1, 234); b.stub(423, +1, None); b.stub(443, +1, 234)
    for hdir, ends in ((-1, (88, None, 72)), (+1, (w - 88, None, w - 72))):
        for y, end in zip((87, 127, 167), ends):
            b.side(y, hdir, end)
    return b


def phone_board() -> Board:
    w = 340
    b = Board(w, 226, (24, 50, 292, 126), 16, [34 + 16 * k for k in range(18)], (6, 7),
              [74, 98, 122, 146], (7, 6), chamfer=5, pulse=12)
    b.bus([34, 50, 66], -1, -1, 8, 8, [12, None, 22])
    b.bus([306, 290, 274], -1, +1, 8, 8, [w - 12, None, w - 22])
    b.bus([114, 130], -1, -1, 8, 8, [96, 84])
    b.bus([226, 210], -1, +1, 8, 8, [w - 96, w - 84])
    b.stub(162, -1, None); b.stub(178, -1, 16)
    b.bus([34, 50, 66], +1, -1, 8, 8, [None, 14, 24])
    b.bus([306, 290, 274], +1, +1, 8, 8, [None, w - 14, w - 24])
    b.bus([114, 130], +1, -1, 8, 8, [96, 84])
    b.bus([226, 210], +1, +1, 8, 8, [w - 96, w - 84])
    b.stub(162, +1, 212); b.stub(178, +1, None)
    for y in (98, 146):
        b.side(y, -1, None); b.side(y, +1, None)
    return b


def wide(f: Fonts, t: dict) -> str:
    b = wide_board()
    runs = []
    for i, part in enumerate(TAGLINE):
        if i:
            runs.append((SEP, "sp"))
        runs.append((part, "tg"))
    board, board_css = board_markup(b, holes=True)
    text, text_css = typed([runs], f, b.cx + b.cw / 2, 163, 0, 16)
    body = board + wordmark(f, b.cx + b.cw / 2, 125, 52) + text
    css = f.css() + variables(t) + "\n" + base_css(len(NAME.replace(" ", "")), b.w) + board_css + "\n" + text_css + "\n"
    return doc(b.w, b.h, LABEL, css, body)


def narrow(f: Fonts) -> str:
    """Both themes in one file, picked by prefers-color-scheme inside the SVG.

    A phone-width <source> must not mention prefers-color-scheme: for anyone
    with an explicit GitHub theme, GitHub's themed-picture script rewrites the
    media of every such source and throws the width condition away - see
    build_project_cards.adaptive_card.
    """
    b = phone_board()
    board, board_css = board_markup(b, holes=False)
    text, text_css = typed([[(part, "tg")] for part in TAGLINE], f, b.cx + b.cw / 2, 117, 18, 13)
    body = board + wordmark(f, b.cx + b.cw / 2, 89, 26) + text
    css = (f.css() + variables(THEMES["dark"]) + "\n"
           + f"@media (prefers-color-scheme: light){{{variables(THEMES['light'])}}}\n"
           + base_css(len(NAME.replace(" ", "")), b.w) + board_css + "\n" + text_css + "\n")
    return doc(b.w, b.h, LABEL, css, body)


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
