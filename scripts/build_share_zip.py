# -*- coding: utf-8 -*-
"""Zip tools/ into tools.zip for sharing.

Default keeps embedded DEFAULT_PASSWORDS. Use --scrub-passwords for external share.

Usage:
  python scripts/build_share_zip.py
  python scripts/build_share_zip.py --scrub-passwords
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

SKIP_DIR_NAMES = {"__pycache__", ".git"}
PASSWORD_LIST_RE = re.compile(
    r"(DEFAULT_PASSWORDS\s*:\s*list\[str\]\s*=\s*\[)(.*?)(\])",
    re.DOTALL,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def scrub_text(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"{match.group(1)}\n    # scrubbed for external share\n{match.group(3)}"

    text = PASSWORD_LIST_RE.sub(repl, text)
    # Soft-scrub common skill doc password sections is left as-is unless list matched.
    return text


def copy_tree(src: Path, dest: Path, *, scrub: bool) -> None:
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        target = dest / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if scrub and path.suffix.lower() in {".py", ".md", ".txt", ".cmd", ".bat"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copy2(path, target)
                continue
            target.write_text(scrub_text(text), encoding="utf-8")
        else:
            shutil.copy2(path, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--scrub-passwords", action="store_true")
    args = parser.parse_args(argv)

    root = (args.repo or repo_root()).resolve()
    tools = root / "tools"
    if not tools.is_dir():
        print(f"Missing tools/: {tools}", file=sys.stderr)
        return 2

    out = args.output or (root / "tools.zip")
    with tempfile.TemporaryDirectory(prefix="tools-share-") as tmp:
        staging = Path(tmp) / "tools"
        staging.mkdir()
        copy_tree(tools, staging, scrub=args.scrub_passwords)
        if out.exists():
            out.unlink()
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in staging.rglob("*"):
                if path.is_file():
                    zf.write(path, arcname=str(Path("tools") / path.relative_to(staging)))
    print(f"Wrote {out} (scrub_passwords={args.scrub_passwords})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
