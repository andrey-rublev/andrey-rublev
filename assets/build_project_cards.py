"""
Renders one card per project into assets/cards/, dark and light.

    python assets/build_project_cards.py

Live metrics (language, stars, forks) come from the GitHub API for the projects
that have a public repo. The blurb and the stack chips stay hand-written here,
because the curated copy in this README is better than the repo descriptions and
several projects - Agentic AI, RealTalk, Gradus - have no repo to read from at
all. So the card is a merge: your words, live numbers.

How two buttons sit on one card
-------------------------------
An SVG inside an <img> is not interactive, so a button painted into the card is
decoration: the click has to come from the <a> wrapping the image, and one image
can carry exactly one link. A card with both a site and a repo is therefore
written out as two 190-wide images, each a window onto the same 380-wide artwork
through its viewBox, each wrapped in its own <a>. Emitted adjacent with no
whitespace between the tags they butt together into one seamless card carrying
two links, and the button drawn in each half is the destination that half goes
to.

The seam has to be vertical. Images on consecutive lines are held apart by the
line box - which is the very gap this layout exists to remove - so the card
cannot instead be sliced into a body and a button row.

Two things worth knowing before editing:

  - Stars are only drawn when non-zero. A grid of "* 0" reads worse than no
    number at all.
  - Every non-ASCII character is emitted as a numeric reference. An SVG has no
    encoding declaration that survives every way it can be served, and the
    em-dashes in these blurbs came back as mojibake without this.
"""
import json
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

# 380 is not arbitrary: GitHub's README column measures 791px, so two cards
# plus their gaps have to fit inside that or they wrap to one per row.
W, H = 380, 188     # box width; artwork is inset by GAP each side
GAP = 5
WRAP = 42
HALF = W // 2

CHIP_Y = 106        # stack chips and the language/star line share this row
DIV_Y = 140         # hairline above the buttons
BTN_Y = 150
BTN_H = 30

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
    {"name": "Agentic AI Infrastructure", "repo": None, "site": None,
     "blurb": "Multi-LLM model routing, MCP servers, custom skills and connectors.",
     "stack": ["MCP", "Python", "TypeScript"]},
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


def pill(kind: str, t: dict, cx: float) -> str:
    """One button, centred on cx in card coordinates.

    The live site is the primary action and takes the solid accent fill; the
    repo is secondary and stays outlined. A card with only one destination
    centres its single button across the whole width.
    """
    label = LABEL[kind]
    icon_w, pad, gap, fs = 13, 13, 7, 12
    w = round(pad + icon_w + gap + len(label) * 6.9 + pad)
    solid = kind == "site"
    fill = t["accent"] if solid else t["chip_bg"]
    ink = t["bg"] if solid else t["chip_fg"]
    stroke = "none" if solid else t["border"]
    return (f'<g transform="translate({cx - w / 2:.1f} {BTN_Y})">'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{BTN_H - 1}" rx="8" fill="{fill}" stroke="{stroke}"/>'
            f'<g transform="translate({pad} {(BTN_H - icon_w) / 2:.1f}) scale({icon_w / 24})">'
            f'<path fill="{ink}" d="{ICONS[kind]}"/></g>'
            f'<text x="{pad + icon_w + gap}" y="{BTN_H / 2 + fs * 0.35:.0f}" class="b" fill="{ink}">{label}</text>'
            f'</g>')


def art(p: dict, t: dict, data: dict, dests: list) -> str:
    """The whole 380-wide card, in card coordinates. Both halves share it."""
    lines = textwrap.wrap(p["blurb"], width=WRAP)[:3]
    body = "".join(
        f'<text x="{GAP+20}" y="{60 + i * 17}" class="d">{esc(l)}</text>'
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

    foot = ""
    if dests:
        foot = (f'<line x1="{GAP+16}" y1="{DIV_Y}" x2="{W-GAP-16}" y2="{DIV_Y}" '
                f'stroke="{t["border"]}"/>')
        # Two buttons each centre on their own half, so each falls entirely
        # inside the image that links to it.
        centres = ([(GAP + W / 2) / 2, (W / 2 + W - GAP) / 2] if len(dests) == 2
                   else [W / 2])
        foot += "".join(pill(kind, t, cx) for (kind, _), cx in zip(dests, centres))

    # The accent bar is clipped to the card, not merely stacked on it: a square
    # bar over a 10px-rounded corner leaves a purple nub poking out at each end.
    return (
        f'<defs><clipPath id="card"><rect x="{GAP+0.5}" y="0.5" width="{W-GAP*2-1}" height="{H-1}" rx="10"/></clipPath></defs>'
        f'<rect x="{GAP+0.5}" y="0.5" width="{W-GAP*2-1}" height="{H-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
        f'<rect x="{GAP+0.5}" y="0.5" width="4" height="{H-1}" fill="{t["accent"]}" clip-path="url(#card)"/>'
        f'<text x="{GAP+20}" y="33" class="t">{esc(p["name"])}</text>'
        + body + "".join(chips) + meta + foot
    )


def card(inner: str, t: dict, label: str, x0: int, vw: int) -> str:
    """Wrap the artwork in an SVG whose viewBox windows it down to one slice."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} 0 {vw} {H}" width="{vw}" height="{H}" role="img" aria-label="{esc(label)}">
<title>{esc(label)}</title>
<style>
  text{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}}
  .t{{font-size:15.5px;font-weight:700;fill:{t['title']}}}
  .d{{font-size:12px;fill:{t['body']}}}
  .c{{font-size:10.5px;fill:{t['chip_fg']};text-anchor:middle}}
  .m{{font-size:11px;fill:{t['meta']}}}
  .e{{text-anchor:end}}
  .b{{font-size:12px;font-weight:600}}
</style>
{inner}
</svg>
"""


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

        for theme_name, t in THEMES.items():
            inner = art(p, t, data, dests)
            if len(dests) == 2:
                for tag, x0, (kind, _) in (("l", 0, dests[0]), ("r", HALF, dests[1])):
                    svg = card(inner, t, f'{p["name"]} {LABEL[kind]}', x0, HALF)
                    ET.fromstring(svg)  # a stray < or & is a silent broken image
                    (OUT / f"{s}-{tag}-{theme_name}.svg").write_text(svg, encoding="utf-8")
            else:
                svg = card(inner, t, p["name"], 0, W)
                ET.fromstring(svg)
                (OUT / f"{s}-{theme_name}.svg").write_text(svg, encoding="utf-8")

        made.append((p, s, data, dests))
        bits = [k for k in ("language", "stars") if data.get(k)]
        print(f"  {p['name']:<26} {len(dests)} link  "
              f"{'live: ' + ', '.join(bits) if bits else 'static'}")

    print(f"\n{len(list(OUT.glob('*.svg')))} files written to assets/cards/\n")
    print("README markup:\n")
    base = "https://raw.githubusercontent.com/andrey-rublev/andrey-rublev/main/assets/cards"

    def pic(stem: str, width: int, alt: str, href: str | None = None) -> str:
        img = (f'<picture>'
               f'<source media="(prefers-color-scheme: dark)" srcset="{base}/{stem}-dark.svg" />'
               f'<source media="(prefers-color-scheme: light)" srcset="{base}/{stem}-light.svg" />'
               f'<img src="{base}/{stem}-dark.svg" alt="{esc(alt)}" width="{width}" />'
               f'</picture>')
        return f'<a href="{href}">{img}</a>' if href else img

    cells = []
    for p, s, _, dests in made:
        if len(dests) == 2:
            cells.append(
                pic(f"{s}-l", HALF, f'{p["name"]} live site', dests[0][1])
                + pic(f"{s}-r", HALF, f'{p["name"]} repository', dests[1][1]))
        elif dests:
            cells.append(pic(s, W, p["name"], dests[0][1]))
        else:
            cells.append(pic(s, W, p["name"]))

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
