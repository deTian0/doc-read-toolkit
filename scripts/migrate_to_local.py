# -*- coding: utf-8 -*-
"""Move root-level date archives into local/YYYY-MM[/DD].

Rules:
  YYYY-MM-DD/...  -> local/YYYY-MM/DD/...
  YYYY-MM/...     -> local/YYYY-MM/...
  索引/           -> local/索引/

Usage:
  python scripts/migrate_to_local.py --dry-run
  python scripts/migrate_to_local.py
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

DAY_RE = re.compile(r"^(\d{4}-\d{2})-(\d{2})$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def plan_moves(root: Path) -> list[tuple[Path, Path]]:
    local = root / "local"
    moves: list[tuple[Path, Path]] = []

    index = root / "索引"
    if index.is_dir():
        moves.append((index, local / "索引"))

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        m_day = DAY_RE.match(child.name)
        if m_day:
            month, day = m_day.group(1), m_day.group(2)
            moves.append((child, local / month / day))
            continue
        if MONTH_RE.match(child.name):
            moves.append((child, local / child.name))
    return moves


def merge_move(src: Path, dest: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"MOVE {src} -> {dest}")
        return
    if dest.exists():
        # Merge directory contents; do not overwrite existing files blindly.
        dest.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            target = dest / item.name
            if target.exists():
                if item.is_dir() and target.is_dir():
                    merge_move(item, target, dry_run=False)
                else:
                    print(f"SKIP exists: {target}", file=sys.stderr)
            else:
                shutil.move(str(item), str(target))
        try:
            src.rmdir()
        except OSError:
            # leftover skipped files
            print(f"KEEP non-empty source: {src}", file=sys.stderr)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        print(f"MOVED {src} -> {dest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None, help="repo root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = (args.root or repo_root()).resolve()
    moves = plan_moves(root)
    if not moves:
        print("Nothing to migrate.")
        return 0

    for src, dest in moves:
        merge_move(src, dest, dry_run=args.dry_run)

    if args.dry_run:
        print(f"Dry-run: {len(moves)} path(s). Re-run without --dry-run to apply.")
    else:
        print(f"Done: {len(moves)} path(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
