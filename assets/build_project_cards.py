"""
Renders one card per project into assets/cards/, dark and light.

    python assets/build_project_cards.py

Live metrics (language, stars, forks) come from the GitHub API for the projects
that have a public repo. The blurb and the stack chips stay hand-written here,
because the curated copy in this README is better than the repo descriptions,
and a project need not have a repo to read from at all. So the card is a
merge: your words, live numbers.

Why only the buttons are links
------------------------------
An SVG inside an <img> is not interactive, so a button painted into the card is
decoration: the click has to come from the <a> wrapping the image, and one image
can carry exactly one link. So a card is written out as several images, each a
window onto the same artwork through its viewBox. A band across the top holds
the title and the buttons, cut into the title, a small box around each button -
each wrapped in its own <a> - and the margin after them. The rest of the card is
one more image under the band. Clicking the card does nothing; clicking a
button goes where the button says. A bare <picture> is left alone by GitHub -
only a bare <img> gets wrapped in a link to the image file.

Phones are the exception: there a card is one image and its buttons a row of
linked pills under it - see PILL_W. That is also what anything that ignores
<source> sees, such as a markdown viewer in an app, because it is what every
<img> falls back to.

The band can sit on the rest of the card because every image has align="top",
one of the few presentational attributes GitHub keeps. Images otherwise sit on
the text baseline, and a line of them keeps room below for descenders, which
opened a gap between consecutive lines of images. Aligned to the top, a line is
exactly as tall as its tallest image, and the next line starts where it ends.

Lines fill left to right, which is why the README markup is not simply card
after card - see the end of main().

Two things worth knowing before editing:

  - Stars are only drawn when non-zero. A grid of "* 0" reads worse than no
    number at all.
  - Every non-ASCII character is emitted as a numeric reference. An SVG has no
    encoding declaration that survives every way it can be served, and the
    em-dashes in these blurbs came back as mojibake without this.
"""
import hashlib
import http.client
import json
import math
import os
import pathlib
import sys
import textwrap
import urllib.request
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "cards"
OUT.mkdir(exist_ok=True)

# 412 is measured, not chosen: two of them fill GitHub's README column, which
# caps at 846px. Two-up, cards are drawn at a share of the column rather than
# at 412 - see WIDE - and one-up they keep it.
W, H = 412, 134     # box width; artwork is inset by GAP each side
GAP = 5
WRAP = 46           # scaled with the card: 42 chars looked right at 380
LINES = 3

TITLE_Y = 31
BLURB_Y, BLURB_LEAD = 54, 16

# Narrow screens get their own artwork, 320 wide, drawn whole - see PILL_W.
# Below a 412px column the pixel widths fail: each <img> shrinks to the column
# on its own, so a card's top band breaks apart across lines. Every card also
# shrinks to ~70%, and 12px body text becomes 8px.
#
# So each <picture> gets narrow sources, and those carry a percentage width:
# <source width> replaces the <img>'s own width when that source is chosen.
# The whole card takes the column, the pills their share of a 320 card, and
# every other piece of the card is nothing.
#
# The column is narrower than 412 below a ~509px viewport, and from 768 to ~796
# where GitHub's profile sidebar appears. Overshooting those bounds is harmless
# - the narrow card just fills the column - so both carry margin for scrollbars.
#
# Narrow cards stack one per line, so each is only as tall as its own blurb.
# The gap between cards is the rule between them - see the end of main().
MW, MWRAP, MLINES = 320, 32, 5
# Upper bounds stop .02px short of the next lower bound: at a zoom or display
# scale the viewport can be a fraction of a pixel wide, and "max-width: 539px"
# and "min-width: 540px" then both miss 539.5.
NARROW = ["(max-width: 539.98px)", "(min-width: 768px) and (max-width: 823.98px)"]
NOT_NARROW = "(min-width: 540px) and (max-width: 767.98px), (min-width: 824px)"

# Phones get each card whole, as one image, and the buttons as a row of linked
# pills under it. Cutting a card into a band of pieces needs every piece to
# scale by exactly the same amount, and WebKit - Safari, and the GitHub app on
# iOS - snaps each image to whole pixels on its own, so the pieces of a card
# came apart at their seams by a pixel or two. One image cannot.
PILL_W = {"site": 104, "repo": 92}
PILL_H, PILL_PAD = 28, 10    # the pill, and the space between it and the card
PILL_TEXT = {"site": "Live site", "repo": "GitHub"}

# The buttons sit on the card rather than under it, so they cost no height.
# They are icon-only because that is what fits: the longest title, "Quantum
# Error Mitigation", measures 190px and ends at x=215, leaving 140px of title
# row. Two labelled pills come to ~138 and would all but touch it.
BTN_W, BTN_H, BTN_GAP = 30, 26, 8
BTN_Y = 12                  # centred on the title's cap height
TOP = BTN_Y + BTN_H + 4     # the band the title and buttons sit in

# Where cards go two to a line, and where one. From ~1012 up the column is the
# viewport less 434px, or 449px with a classic scrollbar, so no breakpoint can
# say exactly where 824px - two cards - starts to fit. Instead, two-up cards
# are sized as a share of the column, 49.9% each, so two always fit and a third
# never does. One-up cards keep their pixel size, so they need a column under
# 824 to be sure of a line each - true below 1240 with either scrollbar. At
# 1240 the two-up cards are ~395 wide; at the 846 cap they are ~422.
WIDE, SINGLE = "(min-width: 1240px)", "(max-width: 1239.98px)"
MID = "(min-width: 540px) and (max-width: 767.98px), (min-width: 824px) and (max-width: 1239.98px)"
HALF = 49.9

THEMES = {
    "dark": {
        "bg": "#0D1117", "border": "#30363D", "accent": "#818CF8", "emblem": 0.42,
        "title": "#E6EDF3", "body": "#8B949E",
        "chip_bg": "#21262D", "chip_fg": "#A5B4FC", "meta": "#7D8590",
    },
    "light": {
        "bg": "#FFFFFF", "border": "#D0D7DE", "accent": "#5B4BD6", "emblem": 0.5,
        "title": "#1F2328", "body": "#57606A",
        "chip_bg": "#EFF1F5", "chip_fg": "#5B4BD6", "meta": "#6E7781",
    },
}

LANG_DOT = {
    "Python": "#3572A5", "TypeScript": "#3178C6", "JavaScript": "#F1E05A",
    "Java": "#B07219", "Dart": "#00B4AB", "C": "#555555", "HTML": "#E34C26",
}

# `site` is a live URL, `repo` is "owner/name". A project can have either, both
# or neither; the card grows a button per destination and links each half to it.
PROJECTS = [
    {"name": "nikhilkolli.com", "repo": "andrey-rublev/NK-Portfolio-Poker",
     "site": "https://nikhilkolli.com",
     "blurb": "My portfolio, dealt as a poker table.",
     "stack": ["TypeScript", "React"]},
    {"name": "GeoGuessr AI", "repo": "andrey-rublev/geoguessr-AI", "site": None,
     "blurb": "Self-trained geolocation model that plays OpenGuessr from screen pixels alone, then finds the spot on the map and drops the pin.",
     "stack": ["PyTorch", "CLIP"]},
    {"name": "SAP-AI", "repo": "andrey-rublev/SAP-AI", "site": None,
     "blurb": "Reinforcement learning agent that plays Super Auto Pets.",
     "stack": ["Python", "RL"]},
    {"name": "Cadence", "repo": "andrey-rublev/cadence", "site": None,
     "blurb": "A second factor made from how you type and click. Learns your sign-in rhythm per site and only asks for a check when unsure.",
     "stack": ["scikit-learn", "FastAPI"]},
    {"name": "Vigil", "repo": "seno3/vigil", "site": None,
     "blurb": "Waze for emergencies. Location-tagged reports scored for credibility by Claude, then pushed to everyone within 10 miles.",
     "stack": ["Next.js", "Supabase", "Mapbox"]},
    {"name": "Raize", "repo": "JuliusZhou124/raize",
     "site": "https://raize-psi.vercel.app",
     "blurb": "Reconstruction planning for disaster zones. Sparse video rebuilt into navigable 3D over UNOSAT damage data.",
     "stack": ["Three.js", "Gemini", "Next.js"]},
]

LABEL = {"site": "Live site", "repo": "Repository"}
ICONS = {
    # simple-icons github mark
    "repo": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    # arrow leaving a box
    "site": "M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7zM5 5h5V3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-5h-2v5H5V5z",
}


# One line-art emblem per project, drawn in a 64x64 box. {c} is the ink and
# {bg} the card, for shapes that have to hide what is behind them.
EMBLEMS = {
    # The portfolio is a poker table: two cards, a spade showing.
    "nikhilkolli.com": (
        '<rect x="12" y="14" width="28" height="38" rx="3.5" transform="rotate(-14 26 33)"/>'
        '<g transform="rotate(10 38 31)"><rect x="24" y="12" width="28" height="38" rx="3.5" fill="{bg}"/>'
        '<path d="M38 22c-4.5 4.5-8 7.2-8 10.6a3.4 3.4 0 0 0 6 2.2L35 39h6l-1-4.2a3.4 3.4 0 0 0 6-2.2'
        'c0-3.4-3.5-6.1-8-10.6z" fill="{c}" stroke="none"/></g>'),
    # A globe, and the pin it drops.
    "GeoGuessr AI": (
        '<circle cx="27" cy="37" r="20"/><ellipse cx="27" cy="37" rx="9" ry="20"/>'
        '<path d="M7 37h40M10 27h34M10 47h34"/>'
        '<path d="M46 5a9 9 0 0 0-9 9c0 6.8 9 16 9 16s9-9.2 9-16a9 9 0 0 0-9-9z" fill="{bg}"/>'
        '<circle cx="46" cy="14" r="3"/>'),
    # A report pinned to the map, and the radius it goes out to.
    "Vigil": (
        '<ellipse cx="32" cy="50" rx="27" ry="9" stroke-dasharray="2.5 3.5"/>'
        '<ellipse cx="32" cy="50" rx="16" ry="5.5"/>'
        '<path d="M32 16a11 11 0 0 0-11 11c0 9.5 11 21 11 21s11-11.5 11-21a11 11 0 0 0-11-11z" fill="{bg}"/>'
        '<circle cx="32" cy="27" r="4"/>'),
    # A building rebuilt as a mesh, vertices and all.
    "Raize": (
        '<path d="M32 8L54 20L32 32L10 20Z"/><path d="M10 20V42L32 54L54 42V20M32 32V54"/>'
        '<path d="M21 14L43 26M43 14L21 26M10 31L32 43L54 31M21 26V48M43 26V48" opacity=".55"/>'
        + "".join(f'<circle cx="{x}" cy="{y}" r="1.8" fill="{{c}}" stroke="none"/>'
                  for x, y in ((32, 8), (54, 20), (32, 32), (10, 20), (10, 42), (32, 54), (54, 42)))),
    "SAP-AI": (
        '<path d="M32 33c-7.5 0-14.5 7.5-14.5 13.5 0 4 3 6.5 7 6.5 3.2 0 4.8-1.6 7.5-1.6s4.3 1.6 7.5 1.6'
        'c4 0 7-2.5 7-6.5 0-6-7-13.5-14.5-13.5z"/>'
        '<ellipse cx="15" cy="30" rx="4.6" ry="6.2" transform="rotate(-22 15 30)"/>'
        '<ellipse cx="25" cy="16" rx="5" ry="6.6" transform="rotate(-8 25 16)"/>'
        '<ellipse cx="39" cy="16" rx="5" ry="6.6" transform="rotate(8 39 16)"/>'
        '<ellipse cx="49" cy="30" rx="4.6" ry="6.2" transform="rotate(22 49 30)"/>'),
    # A keycap, and the rhythm of the keys typed after it.
    "Cadence": (
        '<rect x="5" y="28" width="24" height="24" rx="4"/>'
        '<rect x="9.5" y="31" width="15" height="14" rx="2.5"/>'
        '<path d="M36 52V32M43 52V18M50 52V38M57 52V25" stroke-width="3.5"/>'
        '<path d="M33 56H60" opacity=".55"/>'),
}


def mix(a: str, b: str, t: float) -> str:
    """a blended toward b by t."""
    pa, pb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(pa, pb))


def emblem(name: str, t: dict, right: float, top: float, bottom: float, cap: float) -> str:
    """The project's emblem, right-aligned in the space between the buttons and
    the chip row - or nothing, on a card too short to hold it."""
    size = min(cap, bottom - top)
    if name not in EMBLEMS or size < 30:
        return ""
    s = size / 64
    ink = mix(t["accent"], t["bg"], t["emblem"])
    art = EMBLEMS[name].replace("{c}", ink).replace("{bg}", t["bg"])
    return (f'<g transform="translate({right - size:g} {top + (bottom - top - size) / 2:g}) scale({s:.4f})" '
            f'fill="none" stroke="{ink}" stroke-width="{1.5 / s:.2f}" stroke-linecap="round" stroke-linejoin="round">'
            f"{art}</g>")


def esc(s: str) -> str:
    s = (s.replace("&", "&amp;").replace("<", "&lt;")
          .replace(">", "&gt;").replace('"', "&quot;"))
    return "".join(c if ord(c) < 128 else f"&#{ord(c)};" for c in s)


def api(path: str):
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "andrey-rublev-readme"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def live(repo: str | None) -> dict:
    """Never let an API hiccup break the build - the card still renders."""
    if not repo:
        return {}
    try:
        d = api(f"repos/{repo}")
        return {"language": d.get("language"), "stars": d.get("stargazers_count", 0),
                "forks": d.get("forks_count", 0)}
    except (OSError, http.client.HTTPException, ValueError) as e:  # URLError and dropped connections are OSErrors
        print(f"    {repo}: live data unavailable ({e})", file=sys.stderr)
        return {}


def chip_y(lines: int) -> int:
    """Stack chips and the language/star line share this row, under the blurb."""
    return BLURB_Y + (lines - 1) * BLURB_LEAD + 12


def button_xs(n: int, w: int = W) -> list:
    """Left edges of a right-aligned run of n buttons, in card coordinates."""
    run = n * BTN_W + (n - 1) * BTN_GAP
    right = w - GAP - 20    # the right margin the language/star line uses
    return [right - run + i * (BTN_W + BTN_GAP) for i in range(n)]


def top_cuts(n: int, w: int = W) -> list:
    """x edges of the top band's pieces: the title, a box per button, then the
    margin right of the last button. A box runs half a gap either side of its
    button, so two boxes meet midway between their buttons."""
    xs = button_xs(n, w)
    if not xs:
        return [0, w]
    return ([0] + [round(x - BTN_GAP / 2) for x in xs]
            + [round(xs[-1] + BTN_W + BTN_GAP / 2), w])


def icon_button(kind: str, t: dict, x: float, y: float = BTN_Y) -> str:
    """One button at x, on the title row unless told otherwise.

    The live site is the primary action and takes the solid accent fill; the
    repo is secondary and stays outlined. No label fits here, so the anchor's
    alt text carries the destination.
    """
    solid = kind == "site"
    fill = t["accent"] if solid else t["chip_bg"]
    ink = t["bg"] if solid else t["chip_fg"]
    stroke = "none" if solid else t["border"]
    s = 14
    return (f'<g transform="translate({x} {y})">'
            f'<rect x="0.5" y="0.5" width="{BTN_W - 1}" height="{BTN_H - 1}" rx="7" fill="{fill}" stroke="{stroke}"/>'
            f'<g transform="translate({(BTN_W - s) / 2} {(BTN_H - s) / 2}) scale({s / 24})">'
            f'<path fill="{ink}" d="{ICONS[kind]}"/></g>'
            f'</g>')


def art(p: dict, t: dict, data: dict, dests: list,
        W: int = W, wrap: int = WRAP, max_lines: int = LINES,
        fit: bool = False) -> tuple:
    """The whole card and its height, in card coordinates.

    Every piece of a card shares it. Wide cards reserve max_lines so a row
    of two lines up; `fit` sizes the card to its own blurb instead.
    """
    lines = textwrap.wrap(p["blurb"], width=wrap, break_on_hyphens=False)
    if len(lines) > max_lines:
        print(f"    {p['name']}: blurb cut at {max_lines} lines, {wrap} chars", file=sys.stderr)
    lines = lines[:max_lines]
    CHIP_Y = chip_y(len(lines) if fit else max_lines)
    H = CHIP_Y + 36
    body = "".join(
        f'<text x="{GAP+20}" y="{BLURB_Y + i * BLURB_LEAD}" class="d">{esc(l)}</text>'
        for i, l in enumerate(lines)
    )

    # Stack chips, laid out left to right on an approximate advance width.
    chips, x = [], GAP + 20.0
    for s in p["stack"]:
        w = 11 + len(s) * 6.3
        chips.append(
            f'<rect x="{x:.0f}" y="{CHIP_Y}" width="{w:.0f}" height="20" rx="5" fill="{t["chip_bg"]}"/>'
            f'<text x="{x + w/2:.0f}" y="{CHIP_Y+14}" class="c">{esc(s)}</text>'
        )
        x += w + 6

    # The language and stars close the chip row - or, on a card with no
    # buttons, take the title row's free right side, where three chips on a
    # phone card cannot crowd them.
    meta = ""
    my = TITLE_Y - 1 if not dests else CHIP_Y + 13
    lang = data.get("language")
    if lang:
        meta += f'<circle cx="{W-GAP-104}" cy="{my-4}" r="4.5" fill="{LANG_DOT.get(lang, t["meta"])}"/>'
        meta += f'<text x="{W-GAP-95}" y="{my}" class="m">{esc(lang)}</text>'
    if data.get("stars"):
        meta += f'<text x="{W-GAP-20}" y="{my}" class="m e">&#9733; {data["stars"]}</text>'

    # Right-aligned on the title row, in the same order as `dests` - site then
    # repo - so the cut below lands between them and each button ends up inside
    # the image that links to it.
    buttons = "".join(icon_button(kind, t, x)
                      for (kind, _), x in zip(dests, button_xs(len(dests), W)))
    mark = emblem(p["name"], t, W - GAP - 20, BTN_Y + BTN_H + 6, CHIP_Y - 6, 44 if fit else 48)

    # The surface is flat: one fill and a hairline border, the way GitHub draws
    # its own pinned-repo cards. No glow, no accent stripe along an edge - the
    # emblem and the chips carry the colour.
    x0, cw = GAP + 0.5, W - GAP * 2 - 1
    return (
        f'<rect x="{x0}" y="0.5" width="{cw}" height="{H-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
        f'<text x="{GAP+20}" y="{TITLE_Y}" class="t">{esc(p["name"])}</text>'
        + body + mark + "".join(chips) + meta + buttons
    ), H


FONT = "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}"


def svg_doc(label: str, box: tuple, rules: list, body: str) -> str:
    """An SVG whose viewBox (x, y, w, h) windows the artwork down to one piece."""
    css = "".join(f"  {r}\n" for r in rules)
    x0, y0, vw, vh = box
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {vw} {vh}" width="{vw}" height="{vh}" role="img" aria-label="{esc(label)}">\n'
            f"<title>{esc(label)}</title>\n<style>\n{css}</style>\n{body}\n</svg>\n")


def card(inner: str, t: dict, label: str, box: tuple) -> str:
    """A piece of a card in one theme."""
    return svg_doc(label, box, [
        FONT,
        f".t{{font-size:15.5px;font-weight:700;fill:{t['title']}}}",
        f".d{{font-size:12px;fill:{t['body']}}}",
        f".c{{font-size:10.5px;fill:{t['chip_fg']};text-anchor:middle}}",
        f".m{{font-size:11px;fill:{t['meta']}}}",
        ".e{text-anchor:end}",
    ], inner)


def adaptive_card(layers: dict, label: str, box: tuple) -> str:
    """A card carrying every theme, which picks its own from prefers-color-scheme.

    Narrow sources cannot say which theme they are for. For anyone who has set
    a GitHub theme explicitly, GitHub's themed-picture script rewrites every
    <source> whose media mentions prefers-color-scheme: the chosen theme's get
    "(prefers-color-scheme: light),(prefers-color-scheme: dark)", always true,
    and any width condition alongside is thrown away. The narrow dark card then
    won on desktop too and stretched a phone layout across the column. So the
    narrow <source> tests width alone, and the theme is chosen in here - which
    follows the device's appearance rather than the GitHub setting, the one
    case where the two can disagree.
    """
    rules = [FONT, ".t{font-size:15.5px;font-weight:700}", ".d{font-size:12px}",
             ".c{font-size:10.5px;text-anchor:middle}", ".m{font-size:11px}", ".e{text-anchor:end}"]
    for name, t in THEMES.items():
        rules.append(f".{name} .t{{fill:{t['title']}}} .{name} .d{{fill:{t['body']}}} "
                     f".{name} .c{{fill:{t['chip_fg']}}} .{name} .m{{fill:{t['meta']}}}")
    rules += [".light{display:none}",
              "@media (prefers-color-scheme: light){.dark{display:none}.light{display:inline}}"]
    body = "".join(f'<g class="{name}">{layers[name]}</g>' for name in THEMES)
    return svg_doc(label, box, rules, body)


def pill(kind: str, t: dict) -> str:
    """A labelled button for under a phone card, in one theme."""
    w = PILL_W[kind]
    solid = kind == "site"
    fill = t["accent"] if solid else t["chip_bg"]
    ink = t["bg"] if solid else t["chip_fg"]
    stroke = "none" if solid else t["border"]
    return (f'<rect x="4.5" y="{PILL_PAD + .5}" width="{w - 9}" height="{PILL_H - 1}" rx="8" fill="{fill}" stroke="{stroke}"/>'
            f'<g transform="translate(15 {PILL_PAD + 7}) scale({14 / 24})"><path fill="{ink}" d="{ICONS[kind]}"/></g>'
            f'<text x="35" y="{PILL_PAD + 18.5}" font-size="12" font-weight="600" fill="{ink}">{PILL_TEXT[kind]}</text>')


def pieces(p: dict, dests: list, w: int, h: int) -> list:
    """(file tag, viewBox, label) for each image a card w wide and h tall
    becomes: its top band cut into the title, a box per button and the margin
    after them, then the rest of the card in one piece."""
    xs = top_cuts(len(dests), w)
    tags = ["-t"] + [f"-{kind}-btn" for kind, _ in dests] + (["-tr"] if dests else [])
    labels = ([p["name"]] + [f'{p["name"]} {LABEL[kind]}' for kind, _ in dests]
              + ([p["name"]] if dests else []))
    band = [(tag, (a, 0, b - a, TOP), label) for tag, a, b, label in zip(tags, xs, xs[1:], labels)]
    return band + [("-b", (0, TOP, w, h - TOP), p["name"])]


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")


def main() -> int:
    # A layout change renames files; stale ones would go on being served.
    for old in OUT.glob("*.svg"):
        old.unlink()

    made = []
    for p in PROJECTS:
        data = live(p["repo"])
        s = slug(p["name"])
        dests = []
        if p["site"]:
            dests.append(("site", p["site"]))
        if p["repo"]:
            dests.append(("repo", f'https://github.com/{p["repo"]}'))

        def write(stem: str, svg: str) -> None:
            ET.fromstring(svg)  # a stray < or & is a silent broken image
            (OUT / f"{stem}.svg").write_text(svg, encoding="utf-8")

        # Wide cards: a file per theme, chosen by the <picture> two-up, and one
        # carrying both ("a") for the one-up layout - see adaptive_card.
        wide = {name: art(p, t, data, dests) for name, t in THEMES.items()}
        h = wide["dark"][1]
        for tag, box, label in pieces(p, dests, W, h):
            for theme_name, t in THEMES.items():
                write(f"{s}{tag}-{theme_name}", card(wide[theme_name][0], t, label, box))
            write(f"{s}{tag}-a", adaptive_card({n: a for n, (a, _) in wide.items()}, label, box))

        # Phone cards ("m"): whole and buttonless - the pills under them link.
        # A file per theme, and one carrying both for whatever ignores
        # <source> and so cannot be told the theme.
        def phone(stem: str, layers: dict, label: str, box: tuple) -> None:
            for theme_name, t in THEMES.items():
                write(f"{stem}-{theme_name}", card(layers[theme_name], t, label, box))
            write(stem, adaptive_card(layers, label, box))

        layers = {name: art(p, t, data, [], MW, MWRAP, MLINES, fit=True)
                  for name, t in THEMES.items()}
        phone(f"{s}-m", {n: a for n, (a, _) in layers.items()},
              f'{p["name"]}: {p["blurb"]}', (0, 0, MW, layers["dark"][1]))
        for kind, _ in dests:
            phone(f"{s}-{kind}-pill", {n: pill(kind, t) for n, t in THEMES.items()},
                  f'{p["name"]} {LABEL[kind].lower()}', (0, 0, PILL_W[kind], PILL_PAD + PILL_H))

        made.append((p, s, data, dests))
        bits = [k for k in ("language", "stars") if data.get(k)]
        print(f"  {p['name']:<26} {len(dests)} link  "
              f"{'live: ' + ', '.join(bits) if bits else 'static'}")

    # What a copy of an image shows where it must not: nothing, at no size -
    # even to a renderer that ignores width attributes.
    (OUT / "none.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" viewBox="0 0 1 1"/>\n',
        encoding="utf-8")
    # A spacer: as wide as it is told, never any taller.
    (OUT / "rule.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="0" viewBox="0 0 100 0"/>\n',
        encoding="utf-8")

    print(f"\n{len(list(OUT.glob('*.svg')))} files written to assets/cards/\n")
    print("README markup:\n")
    base = "https://raw.githubusercontent.com/andrey-rublev/andrey-rublev/main/assets/cards"

    def url(stem: str) -> str:
        # File names outlive their contents: a layout change rewrites a card in
        # place, and a phone that had cached the old one kept drawing it - a
        # 36px-tall repo button spliced onto a 142px-tall card. So every URL
        # carries a hash of its file, and new contents are a new cache key.
        # Line endings are normalised so a Windows build hashes like CI's.
        name = f"{stem}.svg"
        digest = hashlib.sha1((OUT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:8]
        return f"{base}/{name}?v={digest}"

    def pic(stem: str, width: int, alt: str, href: str | None, wshare: float,
            show: str = "always") -> str:
        # The first matching <source> wins, so the width-only ones go first;
        # their media must never mention prefers-color-scheme - see
        # adaptive_card. One-up layouts get the wide artwork at its own size,
        # and the two-up layout the themed files as a share of the column.
        # Heights follow the artwork. `show` limits a copy to the two-up
        # layout ("wide") or the one-up ones ("single"); elsewhere it is
        # "none", 0 wide.
        #
        # Phones show none of the pieces, and nor does anything that ignores
        # <source>, whose <img> is nothing - see phone_pic.
        sources = []
        if show == "wide":
            sources.append((SINGLE, "none", ' width="0"'))
        else:
            sources += [(", ".join(NARROW), "none", ' width="0"'),
                        (MID, f"{stem}-a", f' width="{width}"')]
            if show == "single":
                sources.append((WIDE, "none", ' width="0"'))
        if show != "single":
            sources += [(f"(prefers-color-scheme: {th})", f"{stem}-{th}", f' width="{wshare:g}%"')
                        for th in THEMES]
        # align="top" is what lets the bands meet: see the module docstring.
        img = ('<picture>'
               + "".join(f'<source media="{q}" srcset="{url(st)}"{wa} />'
                         for q, st, wa in sources)
               + f'<img src="{url("none")}" width="0" alt="{esc(alt)}" align="top" />'
               '</picture>')
        # The buttons are icon-only, so the hover tooltip is the only place the
        # destination is spelled out for a sighted reader.
        return f'<a href="{href}" title="{esc(alt)}">{img}</a>' if href else img

    def share(px: int, of: int, pct: float = 100) -> float:
        return math.floor(px / of * pct * 100) / 100

    def top(p: dict, s: str, dests: list, show: str = "always") -> str:
        """A card's top band: the title, a linked box per button, the margin."""
        xs = top_cuts(len(dests))
        parts = ([(f"{s}-t", p["name"], None)]
                 + [(f"{s}-{kind}-btn", f'{p["name"]} {LABEL[kind].lower()}', href) for kind, href in dests]
                 + ([(f"{s}-tr", "", None)] if dests else []))
        return "".join(pic(stem, b - a, alt, href, share(b - a, W, HALF), show)
                       for (stem, alt, href), a, b in zip(parts, xs, xs[1:]))

    def phone_pic(stem: str, pct: float, alt: str, href: str | None = None) -> str:
        """An image only phones show. Anything that ignores <source> shows it
        too, in the file carrying both themes, while every piece of the
        wide card falls back to nothing - so what such a viewer gets is the
        phone layout. The theme is the <picture>'s to choose wherever it
        can be: WebKit drew the first card on github.com in the wrong theme
        when the SVG chose for itself."""
        img = ('<picture>'
               f'<source media="{NOT_NARROW}" srcset="{url("none")}" width="0" />'
               + "".join(f'<source media="(prefers-color-scheme: {th})" srcset="{url(f"{stem}-{th}")}" width="{pct:g}%" />'
                         for th in THEMES)
               + f'<img src="{url(stem)}" width="{pct:g}%" alt="{esc(alt)}" align="top" /></picture>')
        return f'<a href="{href}" title="{esc(alt)}">{img}</a>' if href else img

    def bottom(p: dict, s: str, dests: list) -> str:
        """The rest of the card in one piece, its alt text the blurb; then,
        for phones, the whole card and a pill per button."""
        return (pic(f"{s}-b", W, p["blurb"], None, HALF)
                + phone_pic(f"{s}-m", 100, f'{p["name"]}: {p["blurb"]}')
                + "".join(phone_pic(f"{s}-{kind}-pill", share(PILL_W[kind], MW),
                                    f'{p["name"]} {LABEL[kind].lower()}', href)
                          for kind, href in dests))

    def rule(show: str = "always") -> str:
        """A full-width, zero-height image: a line to itself, so whatever comes
        next starts a new one. The line is a text line tall, which is the gap
        between cards."""
        sources = f'<source media="{WIDE}" srcset="{url("none")}" width="0" />' if show == "single" else ""
        return f'<picture>{sources}<img src="{url("rule")}" alt="" width="100%" align="top" /></picture>'

    # All in one paragraph, no table: GitHub strips every style attribute, so a
    # table's cell borders cannot be turned off and they ring each card. No
    # whitespace between tags either - an inline gap would open a seam in
    # every card.
    #
    # Lines fill left to right, so the two-up layout needs both top bands
    # before either bottom band, and the one-up layouts need each card whole
    # before the next. The second card of a pair has its top band written
    # twice to serve both: once where the two-up layout wants it, once where
    # the others do, each copy blank and 0 wide where it does not belong. A
    # rule between the cards of a pair, one-up only, keeps the second card's
    # title off the first card's last line wherever the column could fit both;
    # a rule between pairs does the same in every layout.
    cells = []
    for i in range(0, len(made), 2):
        (pa, sa, _, da), rest = made[i], made[i + 1:i + 2]
        cell = top(pa, sa, da)
        if rest:
            pb, sb, _, db = rest[0]
            cell += (top(pb, sb, db, "wide") + bottom(pa, sa, da) + rule("single")
                     + top(pb, sb, db, "single") + bottom(pb, sb, db))
        else:
            cell += bottom(pa, sa, da)
        cells.append(cell)
    print(f'<p align="center">{rule().join(cells)}</p>')
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
