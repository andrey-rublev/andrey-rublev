"""
Renders one card per project into assets/cards/, dark and light.

    python assets/build_project_cards.py

Live metrics (language, stars, forks) come from the GitHub API for the projects
that have a public repo. The blurb and the stack chips stay hand-written here,
because the curated copy in this README is better than the repo descriptions and
several projects - RealTalk, Gradus - have no repo to read from at
all. So the card is a merge: your words, live numbers.

How two buttons sit on one card
-------------------------------
An SVG inside an <img> is not interactive, so a button painted into the card is
decoration: the click has to come from the <a> wrapping the image, and one image
can carry exactly one link. A card with both a site and a repo is therefore
written out as two images, each a window onto the same 380-wide artwork through
its viewBox, each wrapped in its own <a>. Emitted adjacent with no whitespace
between the tags they butt together into one seamless card carrying two links.

The cut runs between the two buttons rather than down the middle, so each button
lands inside the image that links to it: most of the card for the site, a narrow
strip on the right for the repo.

The cut also has to be vertical, and that is what fixes the buttons side by side
on the title row. Images on consecutive lines are held apart by the line box, so
there is no horizontal cut available - which rules out stacking the two buttons
one above the other, or giving them a row of their own under the card.

Two things worth knowing before editing:

  - Stars are only drawn when non-zero. A grid of "* 0" reads worse than no
    number at all.
  - Every non-ASCII character is emitted as a numeric reference. An SVG has no
    encoding declaration that survives every way it can be served, and the
    em-dashes in these blurbs came back as mojibake without this.
"""
import hashlib
import json
import math
import os
import pathlib
import sys
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "cards"
OUT.mkdir(exist_ok=True)

# 412 is measured, not chosen. GitHub's README column caps at 846px (identical
# at 1440 and 1920 viewports) but is 831px at a 1280-wide window, and two cards
# that overflow the column wrap to one per row instead of shrinking - inline
# images each fit on their own. 831 is therefore the ceiling that matters, and
# 2x412 = 824 clears it while still filling the width. Below ~1150 the column
# drops to ~703 and the grid goes single-column, which is the right fallback.
W, H = 412, 134     # box width; artwork is inset by GAP each side
GAP = 5
WRAP = 46           # scaled with the card: 42 chars looked right at 380
LINES = 3

TITLE_Y = 31
BLURB_Y, BLURB_LEAD = 54, 16

# Narrow screens get their own artwork, same design at 340 wide. Below a 412px
# column the pixel widths fail: each <img> shrinks to the column on its own, so
# a split card's wide half fills the line and its repo strip wraps underneath.
# Every card also shrinks to ~70%, and 12px body text becomes 8px.
#
# So each <picture> gets narrow sources, and those carry a percentage width.
# <source width> replaces the <img>'s own width when that source is chosen, so
# desktop keeps its pixels while on a phone the two halves of a split card take
# fixed shares of the column and scale together, buttons and all. The shares are
# floored to 0.01%: a total a hair over 100% would wrap the strip again, while
# a hair under leaves a seam far below a pixel.
#
# The column is narrower than 412 below a ~509px viewport, and from 768 to ~796
# where GitHub's profile sidebar appears. Overshooting those bounds is harmless
# - the narrow card just fills the column - so both carry margin for scrollbars.
#
# Narrow cards stack one per line, so each is only as tall as its own blurb.
# MPAD is clear space under the card: two cards in one <p> sit a bare line-gap
# apart on a phone while consecutive <p>s get a paragraph margin.
MW, MWRAP, MLINES, MPAD = 340, 38, 4, 8
NARROW = ["(max-width: 539px)", "(min-width: 768px) and (max-width: 823px)"]

# The buttons sit on the card rather than under it, so they cost no height.
# They are icon-only because that is what fits: the longest title, "Quantum
# Error Mitigation", measures 190px and ends at x=215, leaving 140px of title
# row. Two labelled pills come to ~138 and would all but touch it.
BTN_W, BTN_H, BTN_GAP = 30, 26, 8
BTN_Y = 12                  # centred on the title's cap height

THEMES = {
    "dark": {
        "bg": "#0D1117", "border": "#30363D", "accent": "#818CF8",
        "title": "#E6EDF3", "body": "#8B949E",
        "chip_bg": "#21262D", "chip_fg": "#A5B4FC", "meta": "#7D8590",
    },
    "light": {
        "bg": "#FFFFFF", "border": "#D0D7DE", "accent": "#5B4BD6",
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
    {"name": "Quantum-Classical ML", "repo": "andrey-rublev/QML", "site": None,
     "blurb": "Variational circuits classifying ciphers at 96.59% and decrypting at 99.85%, on a 4M+ sample dataset.",
     "stack": ["PennyLane", "PyTorch"]},
    {"name": "Quantum Error Mitigation", "repo": "andrey-rublev/quantum-error-mitigation", "site": None,
     "blurb": "Zero-noise extrapolation recovering H2 ground-state energy from a noisy 4-qubit VQE. Quadratic fit cut error ~10x over linear.",
     "stack": ["PennyLane", "JAX"]},
    {"name": "GeoGuessr AI", "repo": "andrey-rublev/geoguessr-AI", "site": None,
     "blurb": "Self-trained geolocation model that plays OpenGuessr from screen pixels alone, then finds the spot on the map and drops the pin.",
     "stack": ["PyTorch", "CLIP"]},
    {"name": "Vigil", "repo": "seno3/vigil", "site": None,
     "blurb": "Waze for emergencies. Location-tagged reports scored for credibility by Claude, then pushed to everyone within 10 miles.",
     "stack": ["Next.js", "Supabase", "Mapbox"]},
    {"name": "Raize", "repo": "JuliusZhou124/raize",
     "site": "https://raize-psi.vercel.app",
     "blurb": "Reconstruction planning for disaster zones. Sparse video rebuilt into navigable 3D over UNOSAT damage data.",
     "stack": ["Three.js", "Gemini", "Next.js"]},
    {"name": "project-kryptos", "repo": "andrey-rublev/project-kryptos", "site": None,
     "blurb": "Identifies and decodes Caesar, Vigenere, skip and columnar ciphers from ciphertext alone, with no key.",
     "stack": ["Python"]},
    {"name": "RealTalk", "repo": None, "site": None,
     "blurb": "AI hiring assistant that reviews resumes and runs interviews.",
     "stack": ["React", "FastAPI", "AWS"]},
    {"name": "Gradus", "repo": None, "site": None,
     "blurb": "Academic tracking app, shipped to 176 countries.",
     "stack": ["Flutter", "Dart"]},
    {"name": "RLpokerAI", "repo": "andrey-rublev/RLpokerAI", "site": None,
     "blurb": "Reinforcement learning agents for imperfect-information poker.",
     "stack": ["Python", "RL"]},
    {"name": "SAP-AI", "repo": "andrey-rublev/SAP-AI", "site": None,
     "blurb": "Reinforcement learning agent that plays Super Auto Pets.",
     "stack": ["Python", "RL"]},
    {"name": "Networking", "repo": "andrey-rublev/Networking", "site": None,
     "blurb": "Java socket programming and game projects.",
     "stack": ["Java"]},
]

LABEL = {"site": "Live site", "repo": "Repository"}
ICONS = {
    # simple-icons github mark
    "repo": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    # arrow leaving a box
    "site": "M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7zM5 5h5V3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-5h-2v5H5V5z",
}


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
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
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


def split_x(w: int = W) -> int:
    """Where a two-destination card is cut, midway between its two buttons."""
    a, b = button_xs(2, w)
    return round((a + BTN_W + b) / 2)


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

    Both halves of a split card share it. Wide cards reserve max_lines so a row
    of two lines up; `fit` sizes the card to its own blurb instead.
    """
    lines = textwrap.wrap(p["blurb"], width=wrap)
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

    meta = ""
    lang = data.get("language")
    if lang:
        meta += f'<circle cx="{W-GAP-104}" cy="{CHIP_Y+9}" r="4.5" fill="{LANG_DOT.get(lang, t["meta"])}"/>'
        meta += f'<text x="{W-GAP-95}" y="{CHIP_Y+13}" class="m">{esc(lang)}</text>'
    if data.get("stars"):
        meta += f'<text x="{W-GAP-20}" y="{CHIP_Y+13}" class="m e">&#9733; {data["stars"]}</text>'

    # Right-aligned on the title row, in the same order as `dests` - site then
    # repo - so the cut below lands between them and each button ends up inside
    # the image that links to it.
    buttons = "".join(icon_button(kind, t, x)
                      for (kind, _), x in zip(dests, button_xs(len(dests), W)))

    # The accent bar is clipped to the card, not merely stacked on it: a square
    # bar over a 10px-rounded corner leaves a purple nub poking out at each end.
    return (
        f'<defs><clipPath id="card"><rect x="{GAP+0.5}" y="0.5" width="{W-GAP*2-1}" height="{H-1}" rx="10"/></clipPath></defs>'
        f'<rect x="{GAP+0.5}" y="0.5" width="{W-GAP*2-1}" height="{H-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
        f'<rect x="{GAP+0.5}" y="0.5" width="4" height="{H-1}" fill="{t["accent"]}" clip-path="url(#card)"/>'
        f'<text x="{GAP+20}" y="{TITLE_Y}" class="t">{esc(p["name"])}</text>'
        + body + "".join(chips) + meta + buttons
    ), H


FONT = "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}"


def svg_doc(label: str, x0: int, vw: int, H: int, rules: list, body: str) -> str:
    """An SVG whose viewBox windows the artwork down to one slice."""
    css = "".join(f"  {r}\n" for r in rules)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} 0 {vw} {H}" width="{vw}" height="{H}" role="img" aria-label="{esc(label)}">\n'
            f"<title>{esc(label)}</title>\n<style>\n{css}</style>\n{body}\n</svg>\n")


def card(inner: str, t: dict, label: str, x0: int, vw: int, H: int = H) -> str:
    """A card in one theme."""
    return svg_doc(label, x0, vw, H, [
        FONT,
        f".t{{font-size:15.5px;font-weight:700;fill:{t['title']}}}",
        f".d{{font-size:12px;fill:{t['body']}}}",
        f".c{{font-size:10.5px;fill:{t['chip_fg']};text-anchor:middle}}",
        f".m{{font-size:11px;fill:{t['meta']}}}",
        ".e{text-anchor:end}",
    ], inner)


def adaptive_card(layers: dict, label: str, x0: int, vw: int, H: int) -> str:
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
    # Each layer brings its own clip path; the ids have to stay unique.
    body = "".join(f'<g class="{name}">'
                   + layers[name].replace('id="card"', f'id="card-{name}"')
                                 .replace("url(#card)", f"url(#card-{name})")
                   + "</g>" for name in THEMES)
    return svg_doc(label, x0, vw, H, rules, body)


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

        def slices(w: int) -> list:
            """(file tag, x0, width, label) for each image a card of width w becomes."""
            if len(dests) != 2:
                return [("", 0, w, p["name"])]
            cut = split_x(w)
            return [("-l", 0, cut, f'{p["name"]} {LABEL[dests[0][0]]}'),
                    ("-r", cut, w - cut, f'{p["name"]} {LABEL[dests[1][0]]}')]

        # Wide cards: a file per theme, chosen by the <picture>.
        for theme_name, t in THEMES.items():
            inner, h = art(p, t, data, dests)
            for tag, x0, vw, label in slices(W):
                write(f"{s}{tag}-{theme_name}", card(inner, t, label, x0, vw, h))

        # Narrow cards ("m"): one file carrying both themes - see adaptive_card.
        layers = {name: art(p, t, data, dests, MW, MWRAP, MLINES, fit=True)
                  for name, t in THEMES.items()}
        h = layers["dark"][1] + MPAD
        for tag, x0, vw, label in slices(MW):
            write(f"{s}{tag or '-'}m",
                  adaptive_card({n: a for n, (a, _) in layers.items()}, label, x0, vw, h))

        made.append((p, s, data, dests))
        bits = [k for k in ("language", "stars") if data.get(k)]
        print(f"  {p['name']:<26} {len(dests)} link  "
              f"{'live: ' + ', '.join(bits) if bits else 'static'}")

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

    def pic(stem: str, width: int, alt: str, href: str | None = None,
            narrow: str | None = None, share: float = 100) -> str:
        # The first matching <source> wins, so the narrow one goes first,
        # carrying its share of the column; the height follows the artwork. Its
        # media must never mention prefers-color-scheme - see adaptive_card.
        sources = [(", ".join(NARROW), narrow, f' width="{share:g}%"')] if narrow else []
        sources += [(f"(prefers-color-scheme: {th})", f"{stem}-{th}", "") for th in THEMES]
        img = ('<picture>'
               + "".join(f'<source media="{q}" srcset="{url(st)}"{wa} />'
                         for q, st, wa in sources)
               + f'<img src="{url(stem + "-dark")}" alt="{esc(alt)}" width="{width}" />'
               '</picture>')
        # The buttons are icon-only, so the hover tooltip is the only place the
        # destination is spelled out for a sighted reader.
        return f'<a href="{href}" title="{esc(alt)}">{img}</a>' if href else img

    def share(px: int) -> float:
        return math.floor(px / MW * 10000) / 100

    cells = []
    for p, s, _, dests in made:
        if len(dests) == 2:
            cut, mcut = split_x(), split_x(MW)
            cells.append(
                pic(f"{s}-l", cut, f'{p["name"]} live site', dests[0][1], f"{s}-lm", share(mcut))
                + pic(f"{s}-r", W - cut, f'{p["name"]} repository', dests[1][1], f"{s}-rm", share(MW - mcut)))
        elif dests:
            cells.append(pic(s, W, p["name"], dests[0][1], f"{s}-m"))
        else:
            cells.append(pic(s, W, p["name"], narrow=f"{s}-m"))

    # Two per row, no table: GitHub strips every style attribute, so a table's
    # cell borders cannot be turned off and they ring each card. No whitespace
    # between tags either - an inline gap would open a seam down the middle of
    # every split card.
    for i in range(0, len(cells), 2):
        print(f'<p align="center">{"".join(cells[i:i + 2])}</p>')
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
