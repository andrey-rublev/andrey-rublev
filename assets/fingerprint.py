"""
Stamp image URLs in the profile README and its animated header close-up.

    python assets/fingerprint.py

File names outlive their contents. A rebuild rewrites an image in place, and
anything that cached the old one by URL - a phone, GitHub's camo proxy - goes
on drawing it: once that was a stale repo button spliced onto a new card. So
each URL carries ?v=<first 8 hex of the file's sha1>, and new contents are a new
cache key. SVG line endings are normalised first, so a Windows checkout hashes the
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
# Original card images use full raw URLs. Header media use relative URLs so
# a branch preview serves its own animation.
URL = re.compile(
    r'(?P<url>' + re.escape(BASE) + r'assets/[\w./-]+\.svg'
    r'|(?<=")(?:assets/v5/)?(?:wide|mid|mobile|film)(?:-dark)?(?:-still)?\.(?:avif|webp))'
    r'(?:\?v=[0-9a-f]+)?'
)


def digest(path: pathlib.Path) -> str:
    data = path.read_bytes()
    if path.suffix == ".svg":
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(data).hexdigest()[:8]


def main() -> int:
    updates = []
    missing = set()
    for document in (ROOT / "README.md", ROOT / "assets/v5/performance.md"):
        if not document.exists():
            continue

        def stamp(match: re.Match) -> str:
            url = match["url"]
            path = ROOT / url.removeprefix(BASE) if url.startswith(BASE) else document.parent / url
            if not path.is_file():
                missing.add(str(path))
                return match[0]
            return f"{url}?v={digest(path)}"

        text = document.read_text(encoding="utf-8")
        new, count = URL.subn(stamp, text)
        updates.append((document, text, new, count))

    if missing:
        print("missing: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1
    for document, text, new, count in updates:
        if new != text:
            document.write_text(new, encoding="utf-8", newline="\n")
        changed = sum(a != b for a, b in zip(text.splitlines(), new.splitlines()))
        print(f"  {document.name}: {count} URLs stamped, {changed} lines changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
