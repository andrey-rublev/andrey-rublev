"""
Stamps every assets/ URL in README.md with a hash of the file it points at.

    python assets/fingerprint.py

File names outlive their contents. A rebuild rewrites an image in place, and
anything that cached the old one by URL - a phone, GitHub's camo proxy - goes
on drawing it: once that was a stale repo button spliced onto a new card. So
each URL carries ?v=<first 8 hex of the file's sha1>, and new contents are a new
cache key. Line endings are normalised first, so a Windows checkout hashes the
way CI's does. build_project_cards.py stamps the card URLs the same way.

The daily workflows run this after redrawing the contribution graph and the
cards, and commit README.md with them, so those stamps follow the data.
"""
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/andrey-rublev/andrey-rublev/main/"
URL = re.compile(re.escape(BASE) + r"(assets/[\w./-]+\.svg)(?:\?v=[0-9a-f]+)?")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha1(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:8]


def main() -> int:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    missing = []

    def stamp(m: re.Match) -> str:
        path = ROOT / m.group(1)
        if not path.exists():
            missing.append(m.group(1))
            return m.group(0)
        return f"{BASE}{m.group(1)}?v={digest(path)}"

    new, n = URL.subn(stamp, text)
    if missing:
        print("missing: " + ", ".join(sorted(set(missing))), file=sys.stderr)
        return 1
    readme.write_text(new, encoding="utf-8", newline="\n")
    print(f"  {n} URLs stamped, {sum(a != b for a, b in zip(text.splitlines(), new.splitlines()))} lines changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
