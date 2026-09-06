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

W, H = 430, 146
WRAP = 46

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

# repo is "owner/name" when there is a public one to read numbers from.
PROJECTS = [
    {"name": "nikhilkolli.com", "repo": "andrey-rublev/NK-Portfolio-Poker",
     "url": "https://nikhilkolli.com",
     "blurb": "My portfolio, dealt as a poker table.",
     "stack": ["TypeScript", "React"]},
    {"name": "Quantum-Classical ML", "repo": "andrey-rublev/QML",
     "url": "https://github.com/andrey-rublev/QML",
     "blurb": "Variational circuits classifying ciphers at 96.59% and decrypting at 99.85%, on a 4M+ sample dataset.",
     "stack": ["PennyLane", "PyTorch"]},
    {"name": "Quantum Error Mitigation", "repo": "andrey-rublev/quantum-error-mitigation",
     "url": "https://github.com/andrey-rublev/quantum-error-mitigation",
     "blurb": "Zero-noise extrapolation recovering H2 ground-state energy from a noisy 4-qubit VQE. Quadratic fit cut error ~10x over linear.",
     "stack": ["PennyLane", "JAX"]},
    {"name": "Agentic AI Infrastructure", "repo": None, "url": None,
     "blurb": "Multi-LLM model routing, MCP servers, custom skills and connectors.",
     "stack": ["MCP", "Python", "TypeScript"]},
    {"name": "Vigil", "repo": "seno3/vigil",
     "url": "https://github.com/seno3/vigil",
     "blurb": "Waze for emergencies. Location-tagged reports scored for credibility by Claude, then pushed to everyone within 10 miles.",
     "stack": ["Next.js", "Supabase", "Mapbox"]},
    {"name": "Raize", "repo": "JuliusZhou124/raize",
     "url": "https://raize-psi.vercel.app",
     "blurb": "Reconstruction planning for disaster zones. Sparse video rebuilt into navigable 3D over UNOSAT damage data.",
     "stack": ["Three.js", "Gemini", "Next.js"]},
    {"name": "project-kryptos", "repo": "andrey-rublev/project-kryptos",
     "url": "https://github.com/andrey-rublev/project-kryptos",
     "blurb": "Identifies and decodes Caesar, Vigenere, skip and columnar ciphers from ciphertext alone, with no key.",
     "stack": ["Python"]},
    {"name": "RealTalk", "repo": None, "url": None,
     "blurb": "AI hiring assistant that reviews resumes and runs interviews.",
     "stack": ["React", "FastAPI", "AWS"]},
    {"name": "Gradus", "repo": None, "url": None,
     "blurb": "Academic tracking app, shipped to 176 countries.",
     "stack": ["Flutter", "Dart"]},
    {"name": "RLpokerAI", "repo": "andrey-rublev/RLpokerAI",
     "url": "https://github.com/andrey-rublev/RLpokerAI",
     "blurb": "Reinforcement learning agents for imperfect-information games.",
     "stack": ["Python", "RL"]},
    {"name": "Networking", "repo": "andrey-rublev/Networking",
     "url": "https://github.com/andrey-rublev/Networking",
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
        f'<text x="20" y="{60 + i * 17}" class="d">{esc(l)}</text>'
        for i, l in enumerate(lines)
    )

    # Stack chips, laid out left to right on an approximate advance width.
    chips, x = [], 20.0
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
        meta += f'<circle cx="{W-104}" cy="{H-31}" r="4.5" fill="{LANG_DOT.get(lang, t["meta"])}"/>'
        meta += f'<text x="{W-95}" y="{H-27}" class="m">{esc(lang)}</text>'
    if data.get("stars"):
        meta += f'<text x="{W-20}" y="{H-27}" class="m e">&#9733; {data["stars"]}</text>'

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
<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{t['bg']}" stroke="{t['border']}"/>
<rect x="0.5" y="0.5" width="4" height="{H-1}" rx="2" fill="{t['accent']}"/>
<text x="20" y="33" class="t">{esc(p['name'])}</text>
{body}
{"".join(chips)}
{meta}
</svg>
"""


def slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")


def main() -> int:
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
    cells = []
    for p, s, _ in made:
        img = (f'<picture>'
               f'<source media="(prefers-color-scheme: dark)" srcset="{base}/{s}-dark.svg" />'
               f'<source media="(prefers-color-scheme: light)" srcset="{base}/{s}-light.svg" />'
               f'<img src="{base}/{s}-dark.svg" alt="{p["name"]}" width="430" />'
               f'</picture>')
        cells.append(f'<a href="{p["url"]}">{img}</a>' if p["url"] else img)
    # A real HTML table, not a markdown one. A markdown table does not parse
    # inside a raw <div> block, and every soft line break in there becomes a
    # stray <br> - both of which happened. Each <tr> stays on one line for the
    # same reason.
    print("<table>")
    for i in range(0, len(cells), 2):
        row = cells[i:i + 2]
        tds = "".join(f"<td>{c}</td>" for c in row)
        if len(row) == 1:
            tds += "<td></td>"
        print(f"<tr>{tds}</tr>")
    print("</table>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
