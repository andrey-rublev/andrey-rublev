"""
Renders one card per project into assets/cards/, dark and light.

    python assets/build_project_cards.py

Live metrics (language, stars, forks) come from the GitHub API for the projects
that have a public repo. The blurb and the stack chips stay hand-written here,
because the curated copy in this README is better than the repo descriptions and
several projects - Agentic AI, RealTalk, Gradus - have no repo to read from at
all. So the card is a merge: your words, live numbers.

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

W, H = 400, 150     # box width; artwork is inset by GAP each side
GAP = 7
WRAP = 42
BTN_BAR_H = 36

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

# `site` is a live URL, `repo` is "owner/name". A project can have either,
# both, or neither - the card links to whichever exists and a small line under
# it exposes both when there are two, since an image can only carry one link.
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


def card(p: dict, t: dict, data: dict) -> str:
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
            f'<rect x="{x:.0f}" y="{H-40}" width="{w:.0f}" height="20" rx="5" fill="{t["chip_bg"]}"/>'
            f'<text x="{x + w/2:.0f}" y="{H-26}" class="c">{esc(s)}</text>'
        )
        x += w + 6

    meta = ""
    lang = data.get("language")
    if lang:
        meta += f'<circle cx="{W-GAP-104}" cy="{H-31}" r="4.5" fill="{LANG_DOT.get(lang, t["meta"])}"/>'
        meta += f'<text x="{W-GAP-95}" y="{H-27}" class="m">{esc(lang)}</text>'
    if data.get("stars"):
        meta += f'<text x="{W-GAP-20}" y="{H-27}" class="m e">&#9733; {data["stars"]}</text>'

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{esc(p['name'])}">
<title>{esc(p['name'])}</title>
<style>
  text{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}}
  .t{{font-size:15.5px;font-weight:700;fill:{t['title']}}}
  .d{{font-size:12px;fill:{t['body']}}}
  .c{{font-size:10.5px;fill:{t['chip_fg']};text-anchor:middle}}
  .m{{font-size:11px;fill:{t['meta']}}}
  .e{{text-anchor:end}}
</style>
<rect x="{GAP+0.5}" y="0.5" width="{W-GAP*2-1}" height="{H-1}" rx="10" fill="{t['bg']}" stroke="{t['border']}"/>
<rect x="{GAP+0.5}" y="0.5" width="4" height="{H-1}" rx="2" fill="{t['accent']}"/>
<text x="{GAP+20}" y="33" class="t">{esc(p['name'])}</text>
{body}
{"".join(chips)}
{meta}
</svg>
"""



# Buttons have to be separate images, not drawn on the card: an SVG inside an
# <img> is not interactive, so anything painted into the card is decoration
# only. These are shared across every project - the labels never change - and
# each cell links its own copy to its own URL.
BTN_H = 30
ICONS = {
    # simple-icons github mark
    "repo": "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
    # arrow leaving a box
    "site": "M14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7zM5 5h5V3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2v-5h-2v5H5V5z",
}


def button(kind: str, label: str, t: dict, box: int) -> str:
    """A pill centred in a fixed-width transparent box.

    The box width is what does the aligning. Two 200-wide strips sit exactly
    under a 400-wide card, and a lone button gets the full 400 - so the button
    row lines up with the cards above it using nothing but image widths, since
    GitHub strips any CSS that could have done it.
    """
    icon_w, pad, gap, fs = 13, 13, 7, 12
    w = round(pad + icon_w + gap + len(label) * 6.9 + pad)
    x = (box - w) / 2
    y = (BTN_BAR_H - 30) / 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box} {BTN_BAR_H}" width="{box}" height="{BTN_BAR_H}" role="img" aria-label="{label}">
<title>{label}</title>
<g transform="translate({x:.1f} {y:.1f})">
<rect x="0.5" y="0.5" width="{w-1}" height="29" rx="8" fill="{t['chip_bg']}" stroke="{t['border']}"/>
<g transform="translate({pad} {(30-icon_w)/2:.1f}) scale({icon_w/24})"><path fill="{t['chip_fg']}" d="{ICONS[kind]}"/></g>
<text x="{pad + icon_w + gap}" y="{15 + fs*0.35:.0f}" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif" font-size="{fs}" font-weight="600" fill="{t['chip_fg']}">{label}</text>
</g>
</svg>
"""


def spacer(box: int) -> str:
    """Keeps a button-less project occupying its column so the row stays square."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box} {BTN_BAR_H}" '
            f'width="{box}" height="{BTN_BAR_H}" role="presentation"><title> </title>'
            f'<rect width="{box}" height="{BTN_BAR_H}" fill="none"/></svg>')


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")


def main() -> int:
    for kind, label in (("site", "Live site"), ("repo", "Repository")):
        for box in (W // 2, W):          # half a card when paired, full when alone
            for theme_name, t in THEMES.items():
                svg = button(kind, label, t, box)
                ET.fromstring(svg)
                (OUT / f"btn-{kind}-{box}-{theme_name}.svg").write_text(svg, encoding="utf-8")
    for box in (W // 2, W):
        (OUT / f"btn-none-{box}.svg").write_text(spacer(box), encoding="utf-8")

    made = []
    for p in PROJECTS:
        data = live(p["repo"])
        s = slug(p["name"])
        for theme_name, t in THEMES.items():
            svg = card(p, t, data)
            ET.fromstring(svg)  # a stray < or & in the CSS is a silent broken image
            (OUT / f"{s}-{theme_name}.svg").write_text(svg, encoding="utf-8")
        made.append((p, s, data))
        bits = [k for k in ("language", "stars") if data.get(k)]
        print(f"  {p['name']:<26} {'live: ' + ', '.join(bits) if bits else 'static'}")

    print(f"\n{len(made) * 2} cards written to assets/cards/\n")
    print("README markup:\n")
    base = "https://raw.githubusercontent.com/andrey-rublev/andrey-rublev/main/assets/cards"
    HALF = W // 2

    def pic(stem: str, width: int, alt: str, href: str | None) -> str:
        img = (f'<picture>'
               f'<source media="(prefers-color-scheme: dark)" srcset="{base}/{stem}-dark.svg" />'
               f'<source media="(prefers-color-scheme: light)" srcset="{base}/{stem}-light.svg" />'
               f'<img src="{base}/{stem}-dark.svg" alt="{alt}" width="{width}" />'
               f'</picture>')
        return f'<a href="{href}">{img}</a>' if href else img

    cards, bars = [], []
    for p, s, _ in made:
        cards.append(pic(s, W, p["name"], None))

        dests = []
        if p["site"]:
            dests.append(("site", p["site"]))
        if p["repo"]:
            dests.append(("repo", f'https://github.com/{p["repo"]}'))

        if not dests:
            # Still occupies the column, so the row below stays aligned.
            bars.append(f'<img src="{base}/btn-none-{W}.svg" width="{W}" alt="" />')
        else:
            box = HALF if len(dests) == 2 else W
            bars.append("".join(
                pic(f"btn-{kind}-{box}", box, kind, href) for kind, href in dests))

    # Two per row, no table: GitHub strips every style attribute, so a table's
    # cell borders cannot be turned off and they ring each card. Inline images
    # wrap on their own, and the button strips are sized to match the cards
    # above them - alignment done purely with image widths. No whitespace
    # between tags, since an inline gap would break that alignment.
    for i in range(0, len(cards), 2):
        row_cards = "".join(cards[i:i + 2])
        row_bars = "".join(bars[i:i + 2])
        print(f'<p align="center">{row_cards}<br />{row_bars}</p>')
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
