"""
Draws the section headings as silkscreen labels on the board.

    python assets/build_sections.py

Each heading is the index and the name in the banner's lettering - Bungee
over Bungee Shade - between a via and a trace stub. Writes
section-<slug>-dark.svg and -light.svg for each.

The README keeps every one inside a real <h2> with the section name as its alt
text, so it is still a heading to a screen reader and in the page outline;
GitHub's rule under an h2 is left to underline it.

The label is short enough to fit a phone's column as drawn, so unlike the
banner it needs no phone version.
"""
import pathlib
import sys
import xml.etree.ElementTree as ET

from build_hero import THEMES, advances, b64, ensure_subset, ink

HERE = pathlib.Path(__file__).resolve().parent

SECTIONS = [("01", "Projects"), ("02", "Contributions")]
LETTERS = "".join(sorted({c for _, name in SECTIONS for c in name.upper()}))
DIGITS = "".join(sorted({c for i, _ in SECTIONS for c in i}))

SIZE, H, BASE = 20, 32, 24
MONO_SIZE = 12


def main() -> int:
    shade = ensure_subset("Bungee_Shade", "Bungee+Shade", LETTERS, "Bungee_Shade.sections")
    face = ensure_subset("Bungee", "Bungee", LETTERS, "Bungee.sections")
    mono = ensure_subset("JetBrains_Mono_600", "JetBrains+Mono:wght@600", DIGITS, "JetBrains_Mono_600.sections")
    fonts = (f"@font-face{{font-family:'BShade';src:url(data:font/woff2;base64,{b64(shade)}) format('woff2')}}\n"
             f"@font-face{{font-family:'BFace';src:url(data:font/woff2;base64,{b64(face)}) format('woff2')}}\n"
             f"@font-face{{font-family:'JBMono';src:url(data:font/woff2;base64,{b64(mono)}) format('woff2')}}\n")
    mono_w = advances(mono, "0")[0] * MONO_SIZE

    for index, name in SECTIONS:
        label = name.upper()
        # Placed on Shade's advances, as in the banner, so the layers align.
        adv = advances(shade, label)
        right = sum(adv[:-1]) + ink(shade, label[-1])[1]
        x_idx = 28
        x_lab = x_idx + len(index) * mono_w + 10
        end = x_lab + right * SIZE
        w = round(end + 46)
        mid = 17
        # Letter by letter: Shade advances wider than Bungee, so two whole runs
        # set from one x drift apart, the shade trailing off the last letter.
        xs = [x_lab + sum(adv[:i]) * SIZE for i in range(len(label))]
        run = lambda cls: "".join(f'<text class="{cls}" x="{x:.1f}" y="{BASE}">{ch}</text>'
                                  for ch, x in zip(label, xs))
        body = (
            f'<circle class="via" cx="5" cy="{mid}" r="3.2"/>'
            f'<path class="tr" d="M8.2 {mid}H22"/>'
            f'<text class="ix" x="{x_idx}" y="{mid + MONO_SIZE * 0.36:.1f}">{index}</text>'
            f'<g font-size="{SIZE}">{run("sh")}{run("fc")}</g>'
            f'<path class="tr" d="M{end + 10:.1f} {mid}H{w - 14:.1f}l6 -6"/>'
            f'<circle class="via" cx="{w - 5.5:.1f}" cy="{mid - 9.5:.1f}" r="3.2"/>')
        for theme, t in THEMES.items():
            css = (fonts
                   + f".sh{{font-family:'BShade',sans-serif;fill:{t['shade']}}}"
                   f".fc{{font-family:'BFace',sans-serif;fill:{t['face']}}}"
                   f".ix{{font-family:'JBMono',ui-monospace,monospace;font-weight:600;font-size:{MONO_SIZE}px;fill:{t['tag']}}}"
                   f".tr{{fill:none;stroke:{t['via']};stroke-width:1.5;stroke-linejoin:round}}"
                   f".via{{fill:none;stroke:{t['via']};stroke-width:1.5}}\n")
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {H}" width="{w}" height="{H}" '
                   f'role="img" aria-label="{name}">\n<title>{name}</title>\n<style>\n{css}</style>\n{body}\n</svg>\n')
            ET.fromstring(svg)
            out = HERE / f"section-{name.lower()}-{theme}.svg"
            out.write_text(svg, encoding="utf-8")
            print(f"  {out.name:<32} {w}x{H}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
