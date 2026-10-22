"""
Draws the contribution calendar as a populated circuit board, in 3D.

    python assets/build_contrib.py                  # live: GITHUB_TOKEN, else gh
    python assets/build_contrib.py response.json    # a saved GraphQL response

The rest of the README is drawn as a board, and this is its last section: the
past year as a perfboard seen at an angle, one pad per day, the weeks running
from the far corner to the near one. A day with contributions carries a
component - a block whose height follows the count on a square-root scale, so
one 100-commit day does not flatten the rest, and whose shade says where it
ranks among the active days. Empty days are bare pads. The months are printed
on the front edge of the board as silkscreen.

Around it, flat on the page: the year's total in the banner's lettering, the
date range, stars and forks, and the mix of contribution types as LED bar
graphs on a log scale. These are the figures the old graph drew as a radar
chart and a pie, gathered the same way github-profile-3d-contrib gathers them
(languages are those of the repos committed to, weighted by commits).

On load the components are placed week by week, oldest first, like a
pick-and-place pass over the board, and the LED segments light in turn. Reduced
motion keeps the fades and drops the drop. Every resting state is the finished
picture.

Writes contrib-dark.svg and contrib-light.svg, and contrib-m.svg for phones:
the same board at 340 wide, turned further so each day stays a usable size,
theming itself from prefers-color-scheme for the reason given in
build_hero.narrow. The readouts go in the corners the board leaves empty, and
are checked against everything on it, so a tall day cannot run into them.

Runs daily in CI. Fonts come from the committed subsets, so it needs fonttools
and brotli but no network beyond the API.
"""
import json
import math
import os
import pathlib
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from string import printable

from build_hero import advances, b64, ensure_subset, esc, ink

HERE = pathlib.Path(__file__).resolve().parent
LOGIN = os.environ.get("GH_LOGIN", "andrey-rublev")

QUERY = """query($login: String!) { user(login: $login) {
  contributionsCollection {
    contributionCalendar { totalContributions weeks { contributionDays { contributionCount date weekday } } }
    commitContributionsByRepository(maxRepositories: 100) {
      repository { primaryLanguage { name } } contributions { totalCount } }
    totalCommitContributions totalIssueContributions totalPullRequestContributions
    totalPullRequestReviewContributions totalRepositoryContributions }
  repositories(first: 100, ownerAffiliations: OWNER) { nodes { forkCount stargazerCount } } } }"""

# The labels the old radar chart used, in its order.
TYPES = [("Commit", "totalCommitContributions"), ("Issue", "totalIssueContributions"),
         ("PullReq", "totalPullRequestContributions"), ("Review", "totalPullRequestReviewContributions"),
         ("Repo", "totalRepositoryContributions")]

DIGITS = "0123456789,"
ASCII = "".join(c for c in printable if c.isprintable())

# The view: the board turned off square and looked down on at PITCH. Wide
# screens see it nearly side on, a long strip; phones see it turned further,
# corner on, so the weeks run down the column as much as across it and each
# day keeps a usable size.
YAW_WIDE, YAW_PHONE, PITCH = 27, 60, math.radians(36)
GAP, PAD_INSET = 0.13, 0.27          # block and bare-pad inset, in cells
MARGIN = (0.9, 0.9, 1.0, 1.9)        # board margin left, right, back, front
THICK = 5                            # board edge, px

# Timeline, in seconds from load.
BOARD_IN = 0.1
PLACE_AT, PLACE_STEP, PLACE_MS = 0.35, 0.026, 520
NUM_IN = 0.5
LED_AT, LED_STEP = 1.1, 0.045

LED_N = 16
LANG_N = 20

THEMES = {
    "dark": {
        "top": "#0F1422", "front": "#0A0D17", "side": "#080A12", "edge": "#262C36",
        "pad": "#232A42", "silk": "#4B5470", "hole": "#3A4466",
        "l1": "#363194", "l2": "#4F46E5", "l3": "#7B83F6", "l4": "#AEB9FD", "shadow": "#15133A",
        "shade": "#6259E8", "face": "#F0F3F8", "tag": "#A5B4FC", "muted": "#7D8590",
        "on": "#818CF8", "off": "#1B2133", "lang0": "#818CF8", "lang1": "#4F46E5", "lang2": "#3730A3",
    },
    "light": {
        "top": "#F6F7FD", "front": "#E3E6F3", "side": "#D6DAEC", "edge": "#D0D7DE",
        "pad": "#DCE0F2", "silk": "#9AA3B5", "hole": "#B7BDE5",
        "l1": "#D3D9FD", "l2": "#A5B4FC", "l3": "#6366F1", "l4": "#4338CA", "shadow": "#272466",
        "shade": "#7C70E4", "face": "#16181D", "tag": "#4F46E5", "muted": "#6E7781",
        "on": "#5B4BD6", "off": "#E6E8F3", "lang0": "#5B4BD6", "lang1": "#A5B4FC", "lang2": "#D5DAF5",
    },
}
# Each level's two visible sides, darkened from its top toward the theme's shadow.
SIDES = {"front": 0.3, "right": 0.48}


# ------------------------------------------------------------------ the data

def fetch(login: str) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
            headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                     "User-Agent": "andrey-rublev-profile"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
    else:
        # Locally, borrow the GitHub CLI's own sign-in.
        out = subprocess.run(["gh", "api", "graphql", "-f", f"login={login}", "-f", f"query={QUERY}"],
                             capture_output=True, text=True, check=True)
        body = json.loads(out.stdout)
    if body.get("errors"):
        raise RuntimeError(body["errors"][0]["message"])
    return body


def summarise(body: dict) -> dict:
    user = body["data"]["user"]
    cc = user["contributionsCollection"]
    weeks = [[(d["weekday"], d["contributionCount"], d["date"]) for d in w["contributionDays"]]
             for w in cc["contributionCalendar"]["weeks"]]
    langs = {}
    for repo in cc["commitContributionsByRepository"]:
        lang = repo["repository"]["primaryLanguage"]
        if lang:
            langs[lang["name"]] = langs.get(lang["name"], 0) + repo["contributions"]["totalCount"]
    days = [d for w in weeks for d in w]
    return {
        "weeks": weeks,
        "total": cc["contributionCalendar"]["totalContributions"],
        "types": [(label, cc[key]) for label, key in TYPES],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1]),
        "stars": sum(n["stargazerCount"] for n in user["repositories"]["nodes"]),
        "forks": sum(n["forkCount"] for n in user["repositories"]["nodes"]),
        "first": days[0][2], "last": days[-1][2],
    }


def bands(counts: list) -> list:
    """Upper bounds of the first three shades, as percentiles of the active
    days. The brightest is kept for the top tenth, so it reads as a peak."""
    active = sorted(c for c in counts if c)
    if not active:
        return [0, 0, 0]
    return [active[min(len(active) - 1, int(len(active) * q))] for q in (0.4, 0.7, 0.9)]


# ------------------------------------------------------------- the geometry

class View:
    """Projects board coordinates - X along the weeks, Y down the weekdays, in
    cells, Z up in pixels - onto the page."""

    def __init__(self, cell: float, yaw: float, ox: float = 0, oy: float = 0):
        self.yaw = math.radians(yaw)
        c, s, k = math.cos(self.yaw), math.sin(self.yaw), math.sin(PITCH)
        self.ex, self.ey = (cell * c, cell * s * k), (-cell * s, cell * c * k)
        self.ox, self.oy = ox, oy

    def depth(self, X: float, Y: float) -> float:
        return X * math.sin(self.yaw) + Y * math.cos(self.yaw)

    def p(self, X: float, Y: float, Z: float = 0.0) -> tuple:
        return (self.ox + X * self.ex[0] + Y * self.ey[0], self.oy + X * self.ex[1] + Y * self.ey[1] - Z)

    def plane(self, X: float, Y: float, unit: float = 0.1) -> str:
        """A transform that lays text and shapes flat on the board at (X, Y),
        `unit` cells to a user unit - small fonts misrender, so not 1."""
        (a, b), (c, d), (e, f) = self.ex, self.ey, self.p(X, Y)
        return f"matrix({a * unit:.4f} {b * unit:.4f} {c * unit:.4f} {d * unit:.4f} {e:.2f} {f:.2f})"


def poly(pts) -> str:
    return "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z"


def fit(cols: int, yaw: float, width: float, hmax: float, x: float, y: float) -> View:
    """The view whose board fills `width`, its far corner's tallest possible
    component clearing (x, y)."""
    l, r, b, f = MARGIN
    corners = [(X, Y) for X in (-l, cols + r) for Y in (-b, 7 + f)]
    unit = View(1, yaw)
    xs = [unit.p(X, Y)[0] for X, Y in corners]
    cell = width / (max(xs) - min(xs))
    v = View(cell, yaw)
    left = min(v.p(X, Y)[0] for X, Y in corners)
    top = min(v.p(X, Y)[1] for X, Y in corners)
    return View(cell, yaw, x - left, y + hmax - top)


def months(weeks: list) -> list:
    """(column, name) for each month, at the first week it starts. A label
    closer than three weeks to the next one is dropped - in practice the
    partial month the year opens on."""
    marks, prev = [], None
    for i, week in enumerate(weeks):
        m = date.fromisoformat(week[0][2]).strftime("%b").upper()
        if m != prev:
            marks.append((i, m))
        prev = m
    return [(i, m) for (i, m), nxt in zip(marks, marks[1:] + [(len(weeks) + 3, "")])
            if nxt[0] - i >= 3]


def hull(pts: list) -> list:
    """Convex hull, in order (Andrew's monotone chain)."""
    pts = sorted(set(pts))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def overlaps(shape: list, box: tuple) -> bool:
    """Whether a convex polygon and an (x0, y0, x1, y1) box intersect, by
    separating axes."""
    x0, y0, x1, y1 = box
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    axes = [(1, 0), (0, 1)] + [(a[1] - b[1], b[0] - a[0]) for a, b in zip(shape, shape[1:] + shape[:1])]
    for nx, ny in axes:
        ps = [nx * x + ny * y for x, y in shape]
        pb = [nx * x + ny * y for x, y in corners]
        if max(ps) < min(pb) or max(pb) < min(ps):
            return False
    return True


def board(data: dict, v: View, hmax: float, silk_size: float) -> dict:
    """The board, its pads and components, and the silkscreen: markup, CSS,
    the outline of everything drawn (to keep the readouts clear of it), the
    highest point drawn and the bottom of the board's near corner."""
    weeks = data["weeks"]
    cols = len(weeks)
    l, r, b, f = MARGIN
    x0, x1, y0, y1 = -l, cols + r, -b, 7 + f
    shapes = [hull([v.p(X, Y, Z) for X in (x0, x1) for Y in (y0, y1) for Z in (0, -THICK)])]

    top = poly([v.p(x0, y0), v.p(x1, y0), v.p(x1, y1), v.p(x0, y1)])
    front = poly([v.p(x0, y1), v.p(x1, y1), v.p(x1, y1, -THICK), v.p(x0, y1, -THICK)])
    side = poly([v.p(x1, y0), v.p(x1, y1), v.p(x1, y1, -THICK), v.p(x1, y0, -THICK)])
    out = [f'<g class="brd"><path class="bt" d="{top}"/><path class="bf" d="{front}"/><path class="bs" d="{side}"/>']

    # Silkscreen: an outline round the grid, a mounting hole in each corner and
    # the month names along the front margin, all laid flat on the board.
    out.append(f'<path class="silk" d="{poly([v.p(-0.35, -0.35), v.p(cols + 0.35, -0.35), v.p(cols + 0.35, 7.35), v.p(-0.35, 7.35)])}"/>')
    for hx, hy in ((x0 + 0.5, y0 + 0.5), (x1 - 0.5, y0 + 0.5), (x0 + 0.5, y1 - 0.5), (x1 - 0.5, y1 - 0.5)):
        out.append(f'<circle class="hole" r="2.4" transform="{v.plane(hx, hy)}"/>')
    for i, m in months(weeks):
        out.append(f'<text class="silkt" font-size="{silk_size}" transform="{v.plane(i + 0.1, 7.35 + 1.2)}">{m}</text>')
    out.append("</g>")

    # A pad for every day, as one path. The busy days' pads end up under their
    # components, but the board is fully padded before anything is placed.
    pads = []
    a, z = PAD_INSET, 1 - PAD_INSET
    for i, week in enumerate(weeks):
        for wd, _, _ in week:
            pads.append(poly([v.p(i + a, wd + a), v.p(i + z, wd + a), v.p(i + z, wd + z), v.p(i + a, wd + z)]))
    out.append(f'<path class="pad" d="{"".join(pads)}"/>')

    # Components, far to near so nearer ones paint over farther ones.
    counts = [c for week in weeks for _, c, _ in week]
    shade_bounds = bands(counts)
    peak = max(counts) or 1
    k = (hmax - 3) / math.sqrt(peak)
    cells = sorted(((i, wd, c) for i, week in enumerate(weeks) for wd, c, _ in week if c),
                   key=lambda t: v.depth(t[0], t[1]))
    ceiling = min(v.p(X, Y)[1] for X in (x0, x1) for Y in (y0, y1))
    for i, wd, c in cells:
        h = 3 + k * math.sqrt(c)
        lv = 1 + sum(c > bound for bound in shade_bounds)
        a, z = GAP, 1 - GAP
        X0, X1, Y0, Y1 = i + a, i + z, wd + a, wd + z
        ceiling = min(ceiling, v.p(X0, Y0, h)[1])
        shapes.append(hull([v.p(X, Y, Z) for X in (X0, X1) for Y in (Y0, Y1) for Z in (0, h)]))
        out.append(
            f'<g class="cp w{i}">'
            f'<path class="f{lv}" d="{poly([v.p(X0, Y1), v.p(X1, Y1), v.p(X1, Y1, h), v.p(X0, Y1, h)])}"/>'
            f'<path class="r{lv}" d="{poly([v.p(X1, Y0), v.p(X1, Y1), v.p(X1, Y1, h), v.p(X1, Y0, h)])}"/>'
            f'<path class="t{lv}" d="{poly([v.p(X0, Y0, h), v.p(X1, Y0, h), v.p(X1, Y1, h), v.p(X0, Y1, h)])}"/>'
            f'</g>')
    css = "".join(f".w{i}{{animation-delay:{PLACE_AT + i * PLACE_STEP:.3f}s}}" for i in range(cols))
    return {"markup": "".join(out), "css": css, "shapes": shapes,
            "top": ceiling, "bottom": v.p(x1, y1)[1] + THICK}


# --------------------------------------------------------------- the readouts

class Type:
    def __init__(self):
        self.shade = ensure_subset("Bungee_Shade", "Bungee+Shade", DIGITS, "Bungee_Shade.contrib")
        self.face = ensure_subset("Bungee", "Bungee", DIGITS, "Bungee.contrib")
        self.mono = ensure_subset("JetBrains_Mono_600", "JetBrains+Mono:wght@600", ASCII, "JetBrains_Mono_600.contrib")
        self.mono_adv = advances(self.mono, "M")[0]

    def css(self) -> str:
        return "".join(f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{b64(p)}) format('woff2');font-display:block}}\n"
                       for fam, p in (("BShade", self.shade), ("BFace", self.face), ("JBMono", self.mono)))

    def number(self, text: str, right: float, baseline: float, size: float) -> tuple:
        """Digits in two layers, shade under face, set from the right on Shade's
        advances so the layers stay aligned (see build_sections). Returns the
        markup and its width."""
        adv = advances(self.shade, text)
        width = sum(adv[:-1]) * size + ink(self.shade, text[-1])[1] * size
        xs = [right - width + sum(adv[:i]) * size for i in range(len(text))]
        run = lambda cls: "".join(f'<text class="{cls} n{i}" x="{x:.1f}" y="{baseline}">{ch}</text>'
                                  for i, (ch, x) in enumerate(zip(text, xs)))
        return f'<g font-size="{size}">{run("sh")}{run("fc")}</g>', width


STAR = ("M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791"
        "L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z")
FORK = ("M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128"
        "a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"
        "m6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z")


def headline(t: Type, data: dict, right: float, top: float, size: float, small: float) -> tuple:
    """The total, the range and the repo counts, right-aligned in a block.
    Returns the markup and the block's (x0, y0, x1, y1)."""
    cw = t.mono_adv * small
    base = top + size * 0.86
    number, width = t.number(f"{data['total']:,}", right, round(base, 1), size)
    out = [number]
    span = f"{data['first']} / {data['last']}"
    width = max(width, len(span) * cw, len("contributions") * cw * 1.08)
    y = base + small * 1.75
    out.append(f'<text class="mono tag e" x="{right}" y="{y:.1f}" font-size="{small * 1.08:.1f}">contributions</text>')
    y += small * 1.55
    out.append(f'<text class="mono mut e fd" x="{right}" y="{y:.1f}" font-size="{small}">{span}</text>')
    y += small * 1.75
    # Icon, gap, number - laid out right to left.
    x = right
    parts = []
    for icon, n in ((FORK, data["forks"]), (STAR, data["stars"])):
        s = f"{n:,}"
        parts.append(f'<text class="mono fg e" x="{x:.1f}" y="{y:.1f}" font-size="{small}">{s}</text>')
        x -= len(s) * cw + 4 + small
        parts.append(f'<path class="ico" d="{icon}" transform="translate({x:.1f} {y - small * 0.82:.1f}) scale({small / 16:.3f})"/>')
        x -= 14
    out.append(f'<g class="fd">{"".join(parts)}</g>')
    return "".join(out), (right - width, top, right, y + small * 0.3)


def led_bar(x: float, y: float, lit: int, n: int, start: float, led: tuple) -> str:
    lw, lh, lg = led
    out = []
    for i in range(n):
        sx = x + i * (lw + lg)
        out.append(f'<rect class="off" x="{sx}" y="{y}" width="{lw}" height="{lh}" rx="1.5"/>')
        if i < lit:
            out.append(f'<rect class="on led" x="{sx}" y="{y}" width="{lw}" height="{lh}" rx="1.5" '
                       f'style="animation-delay:{start + i * LED_STEP:.3f}s"/>')
    return "".join(out)


def readouts(t: Type, data: dict, x: float, y: float, fs: float, led: tuple, max_w: float) -> tuple:
    """The contribution types as log-scale LED bars, then the languages, in at
    most `max_w`. `led` is a segment's (width, height, gap). Returns markup,
    its height and the boxes its lines fill."""
    lw, lh, lg = led
    cw = t.mono_adv * fs
    label_w = max(len(l) for l, _ in data["types"]) * cw + 10
    bar_x = x + label_w
    bar_w = LED_N * (lw + lg) - lg
    val_x = bar_x + bar_w + 10 + max(len(f"{n:,}") for _, n in data["types"]) * cw
    out, row = [], lh + 5
    for r, (label, n) in enumerate(data["types"]):
        ry = y + r * row
        # One segment per quarter decade: 1 lights the first, 10 the fifth.
        lit = 0 if n < 1 else min(LED_N, 1 + int(4 * math.log10(n) + 1e-9))
        out.append(f'<text class="mono mut" x="{x}" y="{ry + lh - 2}" font-size="{fs}">{label}</text>')
        out.append(led_bar(bar_x, ry, lit, LED_N, LED_AT + r * 0.12, led))
        out.append(f'<text class="mono fg e" x="{val_x:.1f}" y="{ry + lh - 2}" font-size="{fs}">{n:,}</text>')
    sy = y + len(data["types"]) * row + fs * 0.55
    for i, mark in enumerate(("1", "10", "100", "1K")):
        out.append(f'<text class="mono dim" x="{bar_x + i * 4 * (lw + lg):.1f}" y="{sy + 2:.1f}" font-size="{fs * 0.8:.1f}">{mark}</text>')

    # Languages: a bar of segments shared out by commits, the top three lit in
    # their own shades and anything else left dark, with a key under it.
    ly = sy + fs * 1.6
    langs = data["langs"][:3]
    total = sum(n for _, n in data["langs"]) or 1
    shares = [round(LANG_N * n / total) for _, n in langs]
    if langs and len(data["langs"]) <= 3:
        shares[0] += LANG_N - sum(shares)
    out.append(f'<text class="mono mut" x="{x}" y="{ly + lh - 2}" font-size="{fs}">Lang</text>')
    lang_w = (val_x - bar_x) / LANG_N - lg
    lit = [j for j, share in enumerate(shares) for _ in range(share)][:LANG_N]
    for s in range(LANG_N):
        sx = bar_x + s * (lang_w + lg)
        out.append(f'<rect class="off" x="{sx:.1f}" y="{ly}" width="{lang_w:.2f}" height="{lh}" rx="1.5"/>')
        if s < len(lit):
            out.append(f'<rect class="lang{lit[s]} led" x="{sx:.1f}" y="{ly}" width="{lang_w:.2f}" height="{lh}" rx="1.5" '
                       f'style="animation-delay:{LED_AT + 0.7 + s * LED_STEP * 0.6:.3f}s"/>')
    # The key wraps when a long language name would run off the canvas.
    # Line by line rather than one box: the block narrows towards its top,
    # the way the corner it sits in does.
    lines = [(x, y, val_x, ly + lh)]
    key_x, key_y = bar_x, ly + lh + fs * 1.45
    for j, (name, n) in enumerate(langs):
        pct = f"{100 * n / total:.0f}%"
        w = fs * 1.05 + (len(name) + 1 + len(pct)) * cw
        if key_x > bar_x and key_x + w > x + max_w:
            lines.append((bar_x, key_y - fs, key_x - 16, key_y + 3))
            key_x, key_y = bar_x, key_y + fs * 1.5
        out.append(f'<rect class="lang{j}" x="{key_x:.1f}" y="{key_y - fs * 0.72:.1f}" width="{fs * 0.72:.1f}" height="{fs * 0.72:.1f}" rx="1.5"/>'
                   f'<text class="mono fd" x="{key_x + fs * 1.05:.1f}" y="{key_y:.1f}" font-size="{fs}">'
                   f'<tspan class="fg">{esc(name)}</tspan><tspan class="mut"> {pct}</tspan></text>')
        key_x += w + 16
    lines.append((bar_x, key_y - fs, max(bar_x, key_x - 16), key_y + 3))
    return "".join(out), key_y - y + 4, lines


# -------------------------------------------------------------------- output

def variables(t: dict) -> str:
    def mix(a: str, b: str, w: float) -> str:
        ca, cb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{round(x + (y - x) * w):02X}" for x, y in zip(ca, cb))

    v = dict(t)
    for lv in range(1, 5):
        for face, w in SIDES.items():
            v[f"{face[0]}{lv}"] = mix(t[f"l{lv}"], t["shadow"], w)
    return "svg{" + ";".join(f"--{k}:{val}" for k, val in v.items()) + "}"


def base_css() -> str:
    faces = "".join(f".t{lv}{{fill:var(--l{lv})}}.f{lv}{{fill:var(--f{lv})}}.r{lv}{{fill:var(--r{lv})}}" for lv in range(1, 5))
    stagger = "".join(f".n{i}{{animation-delay:{NUM_IN + i * 0.05:.2f}s}}" for i in range(8))
    return (
        ".bt{fill:var(--top);stroke:var(--edge);stroke-width:1;stroke-linejoin:round}"
        ".bf{fill:var(--front);stroke:var(--edge);stroke-width:1;stroke-linejoin:round}"
        ".bs{fill:var(--side);stroke:var(--edge);stroke-width:1;stroke-linejoin:round}\n"
        ".silk{fill:none;stroke:var(--silk);stroke-width:1;stroke-dasharray:3 3}"
        ".hole{fill:none;stroke:var(--hole);stroke-width:1.4;vector-effect:non-scaling-stroke}"
        ".silkt{font-family:'JBMono',ui-monospace,monospace;font-weight:600;fill:var(--silk);letter-spacing:.06em}"
        ".pad{fill:var(--pad)}\n" + faces + "\n"
        ".sh{font-family:'BShade',sans-serif;fill:var(--shade)}.fc{font-family:'BFace',sans-serif;fill:var(--face)}\n"
        ".mono{font-family:'JBMono',ui-monospace,monospace;font-weight:600;white-space:pre}.e{text-anchor:end}\n"
        ".tag{fill:var(--tag)}.mut{fill:var(--muted)}.fg{fill:var(--face)}.dim{fill:var(--silk)}.ico{fill:var(--muted)}\n"
        ".off{fill:var(--off)}.on{fill:var(--on)}.lang0{fill:var(--lang0)}.lang1{fill:var(--lang1)}.lang2{fill:var(--lang2)}\n"
        f".brd,.pad{{animation:fade .5s ease {BOARD_IN}s both}}\n"
        f".cp{{animation:place {PLACE_MS}ms cubic-bezier(.2,.85,.3,1) both}}\n"
        ".sh,.fc{animation:rise .62s cubic-bezier(.2,.85,.3,1) both}" + stagger + "\n"
        f".fd{{animation:fade .5s ease {NUM_IN + 0.4:.2f}s both}}.led{{animation:fade .18s ease-out both}}\n"
        "@keyframes place{from{opacity:0;transform:translateY(-18px)}}\n"
        "@keyframes rise{from{opacity:0;transform:translateY(12px)}}@keyframes fade{from{opacity:0}}\n"
        # Reduced motion keeps what only appears and drops what travels.
        "@media (prefers-reduced-motion: reduce){.cp,.sh,.fc{animation-name:fade}}\n"
    )


def label(data: dict) -> str:
    types = ", ".join(f"{n:,} {l}" for l, n in data["types"])
    langs = ", ".join(n for n, _ in data["langs"][:3])
    return (f"{data['total']:,} contributions from {data['first']} to {data['last']} ({types}); "
            f"languages: {langs}; {data['stars']} stars, {data['forks']} forks")


def doc(w: float, h: float, data: dict, css: str, body: str) -> str:
    text = esc(label(data))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}" '
            f'role="img" aria-label="{text}">\n<title>{text}</title>\n<style>\n{css}</style>\n{body}\n</svg>\n')


def layout(t: Type, data: dict, W: float, pad: float, yaw: float, hmax: float, silk: float,
           head: tuple, fs: float, led: tuple) -> tuple:
    """The board corner to corner across the canvas, the total in the empty
    corner above its near end and the readouts in the one below its far end."""
    v = fit(len(data["weeks"]), yaw, W - 2 * pad, hmax, pad, 0)
    brd = board(data, v, hmax, silk)
    size, small = head
    total, hbox = headline(t, data, W - pad - 2, pad - 2, size, small)
    rx = pad + 4
    reads, rh, lines = readouts(t, data, 0, 0, fs, led, W - rx - pad)

    # The board is drawn `lift` higher than its own coordinates. Both panels
    # are kept 8px clear of everything on it, whatever the year's data does.
    def clear(box: tuple, lift: float) -> bool:
        x0, y0, x1, y1 = box
        box = (x0 - 8, y0 + lift - 8, x1 + 8, y1 + lift + 8)
        return not any(overlaps(s, box) for s in brd["shapes"])

    # The tallest component just under the top edge, unless the total needs
    # the board lower to clear it.
    lift = brd["top"] - pad
    while not clear(hbox, lift):
        lift -= 2
    # The readouts sit low on the left; the canvas grows until they clear.
    H = math.ceil(brd["bottom"] - lift + pad)
    while not all(clear((rx + a, H - pad - rh + b, rx + c, H - pad - rh + d), lift) for a, b, c, d in lines):
        H += 2
    body = (f'<g transform="translate(0 {-lift:.1f})">{brd["markup"]}</g>' + total
            + f'<g transform="translate({rx} {H - rh - pad:.1f})">{reads}</g>')
    return W, H, body, brd["css"]


def wide(t: Type, data: dict) -> tuple:
    return layout(t, data, 846, 10, YAW_WIDE, 62, 9, (44, 12), 11, (7, 11, 2))


def narrow(t: Type, data: dict) -> tuple:
    return layout(t, data, 340, 4, YAW_PHONE, 40, 8.5, (32, 11), 11, (5.5, 10, 1.5))


def main() -> int:
    body = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")) if len(sys.argv) > 1 else fetch(LOGIN)
    data = summarise(body)
    t = Type()
    out = {}
    W, H, markup, css = wide(t, data)
    for name, theme in THEMES.items():
        out[f"contrib-{name}.svg"] = doc(W, H, data, t.css() + variables(theme) + "\n" + base_css() + css + "\n", markup)
    W, H, markup, css = narrow(t, data)
    out["contrib-m.svg"] = doc(W, H, data, t.css() + variables(THEMES["dark"]) + "\n"
                               + f"@media (prefers-color-scheme: light){{{variables(THEMES['light'])}}}\n"
                               + base_css() + css + "\n", markup)
    for name, svg in out.items():
        ET.fromstring(svg)
        (HERE / name).write_text(svg, encoding="utf-8")
        print(f"  {name:<18} {len(svg) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
