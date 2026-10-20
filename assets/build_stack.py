"""
Renders the stack strip under the project grid: one chip per technology.

    python assets/build_stack.py

Replaces a row of shields.io badges, each in its brand's colour, that read as
a rainbow under cards drawn in one accent. The chips here use the cards' chip
language - the same fills, borders and accent - with monochrome icons.

Writes stack-dark.svg and stack-light.svg, two rows sized to the longer one,
and stack-m.svg for phones: three chips a row, both themes in one file, which
picks its own from prefers-color-scheme (see build_project_cards.adaptive_card
for why a phone-width source cannot be told the theme).

Labels are set in an embedded JetBrains Mono, so widths are computed exactly
rather than estimated from whatever sans-serif the viewer has.

Icons are simple-icons paths (CC0), 24x24. Two have none: AWS was withdrawn
from simple-icons, and PennyLane never had one - those are drawn here.
"""
import pathlib
import sys
import xml.etree.ElementTree as ET

from build_hero import advances, b64, ensure_subset

HERE = pathlib.Path(__file__).resolve().parent

STACK = [
    ("Python", "python"), ("TypeScript", "typescript"), ("Java", "openjdk"),
    ("PyTorch", "pytorch"), ("PennyLane", "pennylane"), ("MCP", "modelcontextprotocol"),
    ("React", "react"), ("FastAPI", "fastapi"), ("Next.js", "nextdotjs"),
    ("Three.js", "threedotjs"), ("Flutter", "flutter"), ("AWS", "aws"),
]

MONO = ("JetBrains_Mono_500", "JetBrains+Mono:wght@500", "".join(label for label, _ in STACK))

CH, PAD, IC, GAP, FS = 30, 12, 14, 8, 12     # chip height, padding, icon, icon gap, font size
COL_GAP, ROW_GAP = 8, 8
MW = 340                                      # phone artwork width

THEMES = {
    "dark": {"bg": "#161B22", "border": "#262C36", "icon": "#A5B4FC", "label": "#C9D1D9",
             "trace": "#283050", "via": "#3A4466", "pulse": "#E0E7FF", "glow": "#818CF8"},
    "light": {"bg": "#F6F8FA", "border": "#D0D7DE", "icon": "#5B4BD6", "label": "#24292F",
              "trace": "#D5D9F3", "via": "#B7BDE5", "pulse": "#4F46E5", "glow": "#A5B4FC"},
}

# Each row of chips sits on a bus, as parts sit on the board in the banner: a
# trace runs behind the row and out past both ends to a via, and now and then a
# pulse crosses it - seen only in the gaps, so it seems to pass under the chips.
BUS_PERIOD, BUS_SPEED, BUS_DASH = 9.0, 240, 16

ICONS = {
    "python": "M14.25.18l.9.2.73.26.59.3.45.32.34.34.25.34.16.33.1.3.04.26.02.2-.01.13V8.5l-.05.63-.13.55-.21.46-.26.38-.3.31-.33.25-.35.19-.35.14-.33.1-.3.07-.26.04-.21.02H8.77l-.69.05-.59.14-.5.22-.41.27-.33.32-.27.35-.2.36-.15.37-.1.35-.07.32-.04.27-.02.21v3.06H3.17l-.21-.03-.28-.07-.32-.12-.35-.18-.36-.26-.36-.36-.35-.46-.32-.59-.28-.73-.21-.88-.14-1.05-.05-1.23.06-1.22.16-1.04.24-.87.32-.71.36-.57.4-.44.42-.33.42-.24.4-.16.36-.1.32-.05.24-.01h.16l.06.01h8.16v-.83H6.18l-.01-2.75-.02-.37.05-.34.11-.31.17-.28.25-.26.31-.23.38-.2.44-.18.51-.15.58-.12.64-.1.71-.06.77-.04.84-.02 1.27.05zm-6.3 1.98l-.23.33-.08.41.08.41.23.34.33.22.41.09.41-.09.33-.22.23-.34.08-.41-.08-.41-.23-.33-.33-.22-.41-.09-.41.09zm13.09 3.95l.28.06.32.12.35.18.36.27.36.35.35.47.32.59.28.73.21.88.14 1.04.05 1.23-.06 1.23-.16 1.04-.24.86-.32.71-.36.57-.4.45-.42.33-.42.24-.4.16-.36.09-.32.05-.24.02-.16-.01h-8.22v.82h5.84l.01 2.76.02.36-.05.34-.11.31-.17.29-.25.25-.31.24-.38.2-.44.17-.51.15-.58.13-.64.09-.71.07-.77.04-.84.01-1.27-.04-1.07-.14-.9-.2-.73-.25-.59-.3-.45-.33-.34-.34-.25-.34-.16-.33-.1-.3-.04-.25-.02-.2.01-.13v-5.34l.05-.64.13-.54.21-.46.26-.38.3-.32.33-.24.35-.2.35-.14.33-.1.3-.06.26-.04.21-.02.13-.01h5.84l.69-.05.59-.14.5-.21.41-.28.33-.32.27-.35.2-.36.15-.36.1-.35.07-.32.04-.28.02-.21V6.07h2.09l.14.01zm-6.47 14.25l-.23.33-.08.41.08.41.23.33.33.23.41.08.41-.08.33-.23.23-.33.08-.41-.08-.41-.23-.33-.33-.23-.41-.08-.41.08z",
    "typescript": "M1.125 0C.502 0 0 .502 0 1.125v21.75C0 23.498.502 24 1.125 24h21.75c.623 0 1.125-.502 1.125-1.125V1.125C24 .502 23.498 0 22.875 0zm17.363 9.75c.612 0 1.154.037 1.627.111a6.38 6.38 0 0 1 1.306.34v2.458a3.95 3.95 0 0 0-.643-.361 5.093 5.093 0 0 0-.717-.26 5.453 5.453 0 0 0-1.426-.2c-.3 0-.573.028-.819.086a2.1 2.1 0 0 0-.623.242c-.17.104-.3.229-.393.374a.888.888 0 0 0-.14.49c0 .196.053.373.156.529.104.156.252.304.443.444s.423.276.696.41c.273.135.582.274.926.416.47.197.892.407 1.266.628.374.222.695.473.963.753.268.279.472.598.614.957.142.359.214.776.214 1.253 0 .657-.125 1.21-.373 1.656a3.033 3.033 0 0 1-1.012 1.085 4.38 4.38 0 0 1-1.487.596c-.566.12-1.163.18-1.79.18a9.916 9.916 0 0 1-1.84-.164 5.544 5.544 0 0 1-1.512-.493v-2.63a5.033 5.033 0 0 0 3.237 1.2c.333 0 .624-.03.872-.09.249-.06.456-.144.623-.25.166-.108.29-.234.373-.38a1.023 1.023 0 0 0-.074-1.089 2.12 2.12 0 0 0-.537-.5 5.597 5.597 0 0 0-.807-.444 27.72 27.72 0 0 0-1.007-.436c-.918-.383-1.602-.852-2.053-1.405-.45-.553-.676-1.222-.676-2.005 0-.614.123-1.141.369-1.582.246-.441.58-.804 1.004-1.089a4.494 4.494 0 0 1 1.47-.629 7.536 7.536 0 0 1 1.77-.201zm-15.113.188h9.563v2.166H9.506v9.646H6.789v-9.646H3.375z",
    "openjdk": "M11.915 0 11.7.215C9.515 2.4 7.47 6.39 6.046 10.483c-1.064 1.024-3.633 2.81-3.711 3.551-.093.87 1.746 2.611 1.55 3.235-.198.625-1.304 1.408-1.014 1.939.1.188.823.011 1.277-.491a13.389 13.389 0 0 0-.017 2.14c.076.906.27 1.668.643 2.232.372.563.956.911 1.667.911.397 0 .727-.114 1.024-.264.298-.149.571-.33.91-.5.68-.34 1.634-.666 3.53-.604 1.903.062 2.872.39 3.559.704.687.314 1.15.664 1.925.664.767 0 1.395-.336 1.807-.9.412-.563.631-1.33.72-2.24.06-.623.055-1.32 0-2.066.454.45 1.117.604 1.213.424.29-.53-.816-1.314-1.013-1.937-.198-.624 1.642-2.366 1.549-3.236-.08-.748-2.707-2.568-3.748-3.586C16.428 6.374 14.308 2.394 12.13.215zm.175 6.038a2.95 2.95 0 0 1 2.943 2.942 2.95 2.95 0 0 1-2.943 2.943A2.95 2.95 0 0 1 9.148 8.98a2.95 2.95 0 0 1 2.942-2.942zM8.685 7.983a3.515 3.515 0 0 0-.145.997c0 1.951 1.6 3.55 3.55 3.55 1.95 0 3.55-1.598 3.55-3.55 0-.329-.046-.648-.132-.951.334.095.64.208.915.336a42.699 42.699 0 0 1 2.042 5.829c.678 2.545 1.01 4.92.846 6.607-.082.844-.29 1.51-.606 1.94-.315.431-.713.651-1.315.651-.593 0-.932-.27-1.673-.61-.741-.338-1.825-.694-3.792-.758-1.974-.064-3.073.293-3.821.669-.375.188-.659.373-.911.5s-.466.2-.752.2c-.53 0-.876-.209-1.16-.64-.285-.43-.474-1.101-.545-1.948-.141-1.693.176-4.069.823-6.614a43.155 43.155 0 0 1 1.934-5.783c.348-.167.749-.31 1.192-.425zm-3.382 4.362a.216.216 0 0 1 .13.031c-.166.56-.323 1.116-.463 1.665a33.849 33.849 0 0 0-.547 2.555 3.9 3.9 0 0 0-.2-.39c-.58-1.012-.914-1.642-1.16-2.08.315-.24 1.679-1.755 2.24-1.781zm13.394.01c.562.027 1.926 1.543 2.24 1.783-.246.438-.58 1.068-1.16 2.08a4.428 4.428 0 0 0-.163.309 32.354 32.354 0 0 0-.562-2.49 40.579 40.579 0 0 0-.482-1.652.216.216 0 0 1 .127-.03z",
    "pytorch": "M12.005 0L4.952 7.053a9.865 9.865 0 000 14.022 9.866 9.866 0 0014.022 0c3.984-3.9 3.986-10.205.085-14.023l-1.744 1.743c2.904 2.905 2.904 7.634 0 10.538s-7.634 2.904-10.538 0-2.904-7.634 0-10.538l4.647-4.646.582-.665zm3.568 3.899a1.327 1.327 0 00-1.327 1.327 1.327 1.327 0 001.327 1.328A1.327 1.327 0 0016.9 5.226 1.327 1.327 0 0015.573 3.9z",
    "modelcontextprotocol": "M13.85 0a4.16 4.16 0 0 0-2.95 1.217L1.456 10.66a.835.835 0 0 0 0 1.18.835.835 0 0 0 1.18 0l9.442-9.442a2.49 2.49 0 0 1 3.541 0 2.49 2.49 0 0 1 0 3.541L8.59 12.97l-.1.1a.835.835 0 0 0 0 1.18.835.835 0 0 0 1.18 0l.1-.098 7.03-7.034a2.49 2.49 0 0 1 3.542 0l.049.05a2.49 2.49 0 0 1 0 3.54l-8.54 8.54a1.96 1.96 0 0 0 0 2.755l1.753 1.753a.835.835 0 0 0 1.18 0 .835.835 0 0 0 0-1.18l-1.753-1.753a.266.266 0 0 1 0-.394l8.54-8.54a4.185 4.185 0 0 0 0-5.9l-.05-.05a4.16 4.16 0 0 0-2.95-1.218c-.2 0-.401.02-.6.048a4.17 4.17 0 0 0-1.17-3.552A4.16 4.16 0 0 0 13.85 0m0 3.333a.84.84 0 0 0-.59.245L6.275 10.56a4.186 4.186 0 0 0 0 5.902 4.186 4.186 0 0 0 5.902 0L19.16 9.48a.835.835 0 0 0 0-1.18.835.835 0 0 0-1.18 0l-6.985 6.984a2.49 2.49 0 0 1-3.54 0 2.49 2.49 0 0 1 0-3.54l6.983-6.985a.835.835 0 0 0 0-1.18.84.84 0 0 0-.59-.245",
    "react": "M14.23 12.004a2.236 2.236 0 0 1-2.235 2.236 2.236 2.236 0 0 1-2.236-2.236 2.236 2.236 0 0 1 2.235-2.236 2.236 2.236 0 0 1 2.236 2.236zm2.648-10.69c-1.346 0-3.107.96-4.888 2.622-1.78-1.653-3.542-2.602-4.887-2.602-.41 0-.783.093-1.106.278-1.375.793-1.683 3.264-.973 6.365C1.98 8.917 0 10.42 0 12.004c0 1.59 1.99 3.097 5.043 4.03-.704 3.113-.39 5.588.988 6.38.32.187.69.275 1.102.275 1.345 0 3.107-.96 4.888-2.624 1.78 1.654 3.542 2.603 4.887 2.603.41 0 .783-.09 1.106-.275 1.374-.792 1.683-3.263.973-6.365C22.02 15.096 24 13.59 24 12.004c0-1.59-1.99-3.097-5.043-4.032.704-3.11.39-5.587-.988-6.38-.318-.184-.688-.277-1.092-.278zm-.005 1.09v.006c.225 0 .406.044.558.127.666.382.955 1.835.73 3.704-.054.46-.142.945-.25 1.44-.96-.236-2.006-.417-3.107-.534-.66-.905-1.345-1.727-2.035-2.447 1.592-1.48 3.087-2.292 4.105-2.295zm-9.77.02c1.012 0 2.514.808 4.11 2.28-.686.72-1.37 1.537-2.02 2.442-1.107.117-2.154.298-3.113.538-.112-.49-.195-.964-.254-1.42-.23-1.868.054-3.32.714-3.707.19-.09.4-.127.563-.132zm4.882 3.05c.455.468.91.992 1.36 1.564-.44-.02-.89-.034-1.345-.034-.46 0-.915.01-1.36.034.44-.572.895-1.096 1.345-1.565zM12 8.1c.74 0 1.477.034 2.202.093.406.582.802 1.203 1.183 1.86.372.64.71 1.29 1.018 1.946-.308.655-.646 1.31-1.013 1.95-.38.66-.773 1.288-1.18 1.87-.728.063-1.466.098-2.21.098-.74 0-1.477-.035-2.202-.093-.406-.582-.802-1.204-1.183-1.86-.372-.64-.71-1.29-1.018-1.946.303-.657.646-1.313 1.013-1.954.38-.66.773-1.286 1.18-1.868.728-.064 1.466-.098 2.21-.098zm-3.635.254c-.24.377-.48.763-.704 1.16-.225.39-.435.782-.635 1.174-.265-.656-.49-1.31-.676-1.947.64-.15 1.315-.283 2.015-.386zm7.26 0c.695.103 1.365.23 2.006.387-.18.632-.405 1.282-.66 1.933-.2-.39-.41-.783-.64-1.174-.225-.392-.465-.774-.705-1.146zm3.063.675c.484.15.944.317 1.375.498 1.732.74 2.852 1.708 2.852 2.476-.005.768-1.125 1.74-2.857 2.475-.42.18-.88.342-1.355.493-.28-.958-.646-1.956-1.1-2.98.45-1.017.81-2.01 1.085-2.964zm-13.395.004c.278.96.645 1.957 1.1 2.98-.45 1.017-.812 2.01-1.086 2.964-.484-.15-.944-.318-1.37-.5-1.732-.737-2.852-1.706-2.852-2.474 0-.768 1.12-1.742 2.852-2.476.42-.18.88-.342 1.356-.494zm11.678 4.28c.265.657.49 1.312.676 1.948-.64.157-1.316.29-2.016.39.24-.375.48-.762.705-1.158.225-.39.435-.788.636-1.18zm-9.945.02c.2.392.41.783.64 1.175.23.39.465.772.705 1.143-.695-.102-1.365-.23-2.006-.386.18-.63.406-1.282.66-1.933zM17.92 16.32c.112.493.2.968.254 1.423.23 1.868-.054 3.32-.714 3.708-.147.09-.338.128-.563.128-1.012 0-2.514-.807-4.11-2.28.686-.72 1.37-1.536 2.02-2.44 1.107-.118 2.154-.3 3.113-.54zm-11.83.01c.96.234 2.006.415 3.107.532.66.905 1.345 1.727 2.035 2.446-1.595 1.483-3.092 2.295-4.11 2.295-.22-.005-.406-.05-.553-.132-.666-.38-.955-1.834-.73-3.703.054-.46.142-.944.25-1.438zm4.56.64c.44.02.89.034 1.345.034.46 0 .915-.01 1.36-.034-.44.572-.895 1.095-1.345 1.565-.455-.47-.91-.993-1.36-1.565z",
    "fastapi": "M12 .0387C5.3729.0384.0003 5.3931 0 11.9988c-.001 6.6066 5.372 11.9628 12 11.9625 6.628.0003 12.001-5.3559 12-11.9625-.0003-6.6057-5.3729-11.9604-12-11.96m-.829 5.4153h7.55l-7.5805 5.3284h5.1828L5.279 18.5436q2.9466-6.5444 5.892-13.0896",
    "nextdotjs": "M18.665 21.978C16.758 23.255 14.465 24 12 24 5.377 24 0 18.623 0 12S5.377 0 12 0s12 5.377 12 12c0 3.583-1.574 6.801-4.067 9.001L9.219 7.2H7.2v9.596h1.615V9.251l9.85 12.727Zm-3.332-8.533 1.6 2.061V7.2h-1.6v6.245Z",
    "threedotjs": "M.38 0a.268.268 0 0 0-.256.332l2.894 11.716a.268.268 0 0 0 .01.04l2.89 11.708a.268.268 0 0 0 .447.128L23.802 7.15a.268.268 0 0 0-.112-.45l-5.784-1.667a.268.268 0 0 0-.123-.035L6.38 1.715a.268.268 0 0 0-.144-.04L.456.01A.268.268 0 0 0 .38 0zm.374.654L5.71 2.08 1.99 5.664zM6.61 2.34l4.864 1.4-3.65 3.515zm-.522.12l1.217 4.926-4.877-1.4zm6.28 1.538l4.878 1.404-3.662 3.53zm-.52.13l1.208 4.9-4.853-1.392zm6.3 1.534l4.947 1.424-3.715 3.574zm-.524.12l1.215 4.926-4.876-1.398zm-15.432.696l4.964 1.424-3.726 3.586zM8.047 8.15l4.877 1.4-3.66 3.527zm-.518.137l1.236 5.017-4.963-1.432zm6.274 1.535l4.965 1.425-3.73 3.586zm-.52.127l1.235 5.012-4.958-1.43zm-9.63 2.438l4.873 1.406-3.656 3.523zm5.854 1.687l4.863 1.403-3.648 3.51zm-.54.04l1.214 4.927-4.875-1.4zm-3.896 4.02l5.037 1.442-3.782 3.638z",
    "flutter": "M14.314 0L2.3 12 6 15.7 21.684.013h-7.357zm.014 11.072L7.857 17.53l6.47 6.47H21.7l-6.46-6.468 6.46-6.46h-7.37z",
}

# Drawn rather than borrowed: a Bloch sphere for PennyLane, a cloud for AWS.
GLYPHS = {
    "pennylane": ('<circle cx="12" cy="12" r="9.5" fill="none" stroke-width="2"/>'
                  '<ellipse cx="12" cy="12" rx="9.5" ry="3.4" fill="none" stroke-width="1.5"/>'
                  '<path d="M12 12 17.2 5.6" fill="none" stroke-width="2" stroke-linecap="round"/>'
                  '<circle cx="17.6" cy="5.1" r="2.4" stroke="none"/>'),
    # Material Icons "cloud" (Apache-2.0)
    "aws": '<path stroke="none" d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z"/>',
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def glyph(key: str) -> str:
    return GLYPHS[key] if key in GLYPHS else f'<path d="{ICONS[key]}"/>'


def chip_width(label: str, adv: float) -> float:
    return PAD + IC + GAP + len(label) * adv * FS + PAD


def rows_balanced(widths: list, n_rows: int) -> list:
    """Split into n_rows consecutive runs, keeping the widest run as narrow as possible."""
    best = None
    def span(a, b):
        return sum(widths[a:b]) + COL_GAP * (b - a - 1)
    def go(start, left, cuts):
        nonlocal best
        if left == 1:
            parts = cuts + [(start, len(widths))]
            worst = max(span(a, b) for a, b in parts)
            if best is None or worst < best[0]:
                best = (worst, parts)
            return
        for end in range(start + 1, len(widths) - left + 2):
            go(end, left - 1, cuts + [(start, end)])
    go(0, n_rows, [])
    return best[1]


def rows_greedy(widths: list, max_w: float) -> list:
    rows, start, used = [], 0, 0.0
    for i, w in enumerate(widths):
        need = w if i == start else used + COL_GAP + w
        if need > max_w and i > start:
            rows.append((start, i))
            start, used = i, w
        else:
            used = need
    rows.append((start, len(widths)))
    return rows


def layout(widths: list, rows: list, canvas: float) -> list:
    """(x, y) per chip, each row centred on the canvas."""
    pos = [None] * len(widths)
    for r, (a, b) in enumerate(rows):
        span = sum(widths[a:b]) + COL_GAP * (b - a - 1)
        x = (canvas - span) / 2
        for i in range(a, b):
            pos[i] = (round(x, 2), r * (CH + ROW_GAP))
            x += widths[i] + COL_GAP
    return pos


def chips(widths: list, pos: list) -> str:
    out = []
    for (label, key), w, (x, y) in zip(STACK, widths, pos):
        out.append(
            f'<g transform="translate({x} {y})">'
            f'<rect class="chip" x="0.5" y="0.5" width="{w - 1:.2f}" height="{CH - 1}" rx="8"/>'
            f'<g class="ic" transform="translate({PAD} {(CH - IC) / 2}) scale({IC / 24})">{glyph(key)}</g>'
            f'<text class="lb" x="{PAD + IC + GAP}" y="{CH / 2 + FS * 0.36:.2f}">{esc(label)}</text>'
            f'</g>')
    return "".join(out)


def buses(widths: list, rows: list, pos: list, ext: float) -> tuple:
    """A trace under each row, its vias, and its pulse. Returns markup and CSS."""
    out, css = [], []
    for r, (a, b) in enumerate(rows):
        x0, x1 = pos[a][0] - ext, pos[b - 1][0] + widths[b - 1] + ext
        y, n = pos[a][1] + CH / 2, x1 - x0
        d = f"M{x0:.2f} {y}H{x1:.2f}"
        q = n / BUS_SPEED / BUS_PERIOD * 100
        delay = 1.2 + r * 1.6
        css.append(f"@keyframes s{r}{{0%{{stroke-dashoffset:{BUS_DASH + 4}}}{q:.2f}%,100%{{stroke-dashoffset:{-(n + 4):.1f}}}}}")
        anim = f"s{r} {BUS_PERIOD}s cubic-bezier(.4,0,.6,1) {delay:.2f}s infinite both"
        out.append(f'<path class="bus" d="{d}"/>'
                   + "".join(f'<path class="{c}" d="{d}" style="stroke-dasharray:{BUS_DASH} {n + 40:.0f};animation:{anim}"/>'
                             for c in ("glo", "pul"))
                   + f'<circle class="via" cx="{x0:.2f}" cy="{y}" r="3"/><circle class="via" cx="{x1:.2f}" cy="{y}" r="3"/>')
    return "".join(out), "".join(css)


def colours(t: dict) -> str:
    """A theme as custom properties, so the chips are drawn once whatever the theme."""
    return (f"svg{{--bg:{t['bg']};--bd:{t['border']};--ic:{t['icon']};--lb:{t['label']};"
            f"--tr:{t['trace']};--via:{t['via']};--pu:{t['pulse']};--gl:{t['glow']}}}")


def doc(w: float, h: float, css: str, body: str) -> str:
    label = "Stack: " + ", ".join(label for label, _ in STACK)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:g} {h:g}" width="{w:g}" height="{h:g}" '
            f'role="img" aria-label="{label}">\n<title>{label}</title>\n<style>\n{css}</style>\n{body}\n</svg>\n')


def main() -> int:
    font = ensure_subset(*MONO)
    adv = advances(font, "M")[0]
    base = (f"@font-face{{font-family:'JBMono';src:url(data:font/woff2;base64,{b64(font)}) format('woff2');font-display:block}}\n"
            f".lb{{font-family:'JBMono',ui-monospace,monospace;font-size:{FS}px;font-weight:500;fill:var(--lb)}}\n"
            ".chip{fill:var(--bg);stroke:var(--bd)}.ic{fill:var(--ic);stroke:var(--ic)}\n"
            ".bus{fill:none;stroke:var(--tr);stroke-width:1.5}.via{fill:none;stroke:var(--via);stroke-width:1.5}\n"
            ".glo{fill:none;stroke:var(--gl);stroke-opacity:.35;stroke-width:6;stroke-linecap:round}\n"
            ".pul{fill:none;stroke:var(--pu);stroke-width:1.7;stroke-linecap:round}\n"
            "@media (prefers-reduced-motion: reduce){.glo,.pul{display:none}}\n")
    widths = [chip_width(label, adv) for label, _ in STACK]

    out = {}
    ext = 22
    rows = rows_balanced(widths, 2)
    w = max(sum(widths[a:b]) + COL_GAP * (b - a - 1) for a, b in rows)
    w = int(w + 2 * ext) + 6
    h = len(rows) * CH + (len(rows) - 1) * ROW_GAP
    pos = layout(widths, rows, w)
    wires, wire_css = buses(widths, rows, pos, ext)
    body = wires + chips(widths, pos)
    for name, t in THEMES.items():
        out[f"stack-{name}.svg"] = doc(w, h, base + colours(t) + "\n" + wire_css + "\n", body)

    rows = rows_greedy(widths, MW - 2 * 18)
    h = len(rows) * CH + (len(rows) - 1) * ROW_GAP
    pos = layout(widths, rows, MW)
    wires, wire_css = buses(widths, rows, pos, 14)
    body = wires + chips(widths, pos)
    css = (base + colours(THEMES["dark"]) + "\n"
           + f"@media (prefers-color-scheme: light){{{colours(THEMES['light'])}}}\n" + wire_css + "\n")
    out["stack-m.svg"] = doc(MW, h, css, body)

    for name, svg in out.items():
        ET.fromstring(svg)  # a stray < or & is a silent broken image
        (HERE / name).write_text(svg, encoding="utf-8")
        print(f"  {name:<16} {len(svg) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
