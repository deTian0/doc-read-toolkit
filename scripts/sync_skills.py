# -*- coding: utf-8 -*-
"""Sync tools/.claude/skills -> <repo>/.claude/skills for Claude Code.

By default substitutes YOUR_DOC_ROOT with the repo root so local .cmd works
without requiring every collaborator to edit placeholders.

Usage:
  python scripts/sync_skills.py
  python scripts/sync_skills.py --check
  python scripts/sync_skills.py --keep-placeholders
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

SKIP_DIR_NAMES = {"__pycache__", ".git"}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".cmd",
    ".bat",
    ".txt",
    ".json",
    ".html",
    ".yml",
    ".yaml",
    ".toml",
    ".css",
    ".js",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def iter_files(src_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        files.append(path)
    return files


def transform_text(text: str, doc_root: str | None) -> str:
    if not doc_root:
        return text
    # Normalize common placeholder spellings to the real local root.
    slash = doc_root.replace("\\", "/")
    back = doc_root.replace("/", "\\")
    out = text
    out = out.replace("YOUR_DOC_ROOT", slash)
    # Windows cmd examples often need backslashes.
    out = out.replace(slash + "\\.conda", back + "\\.conda")
    out = out.replace(slash + "/.conda", back + "\\.conda")
    # Prefer backslash form inside .cmd after substitution of PY= lines —
    # handled per-file below when needed.
    return out


def sync_file(src: Path, dest: Path, doc_root: str | None, *, dry: bool) -> bool:
    """Return True if dest would change."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    if src.suffix.lower() in TEXT_SUFFIXES or src.name.lower() in {"skill.md"}:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            new_text = transform_text(text, doc_root)
            if src.suffix.lower() == ".cmd" and doc_root:
                # .cmd path to python.exe should use backslashes on Windows.
                back = doc_root.replace("/", "\\")
                slash = doc_root.replace("\\", "/")
                new_text = new_text.replace(
                    f"{slash}\\.conda\\doc-read\\python.exe",
                    f"{back}\\.conda\\doc-read\\python.exe",
                )
                new_text = new_text.replace(
                    f"{slash}/.conda/doc-read/python.exe",
                    f"{back}\\.conda\\doc-read\\python.exe",
                )
            new_raw = new_text.encode("utf-8")
            if dest.exists() and dest.read_bytes() == new_raw:
                return False
            if not dry:
                dest.write_bytes(new_raw)
            return True

    if dest.exists() and filecmp.cmp(src, dest, shallow=False):
        return False
    if not dry:
        shutil.copy2(src, dest)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="exit 1 if out of sync")
    parser.add_argument(
        "--keep-placeholders",
        action="store_true",
        help="copy verbatim without substituting YOUR_DOC_ROOT",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = (args.repo or repo_root()).resolve()
    src_root = root / "tools" / ".claude" / "skills"
    dest_root = root / ".claude" / "skills"
    if not src_root.is_dir():
        print(f"Missing tools skills: {src_root}", file=sys.stderr)
        return 2

    doc_root = None if args.keep_placeholders else str(root).replace("\\", "/")
    changed = 0
    for src in iter_files(src_root):
        rel = src.relative_to(src_root)
        dest = dest_root / rel
        if sync_file(src, dest, doc_root, dry=args.check or args.dry_run):
            changed += 1
            print(f"{'WOULD UPDATE' if args.check or args.dry_run else 'UPDATE'} {rel}")

    if args.check:
        if changed:
            print(f"Out of sync: {changed} file(s). Run: python scripts/sync_skills.py")
            return 1
        print("Skills in sync.")
        return 0

    print(f"Synced {changed} file(s) -> {dest_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
