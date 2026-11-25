# -*- coding: utf-8 -*-
"""Read a UTF-8 .env file and emit a GBK .bat snippet that sets unset vars.

Usage:
  python load_dotenv_bat.py <env-file> <out-bat>
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: load_dotenv_bat.py <env-file> <out-bat>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    dst = Path(argv[2])
    if not src.is_file():
        dst.write_bytes(b"")
        return 0

    text = src.read_text(encoding="utf-8-sig")
    lines: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, val = s.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        # Escape for: set "KEY=VALUE"
        val = val.replace('%', '%%').replace('"', '""')
        lines.append(f'if not defined {key} set "{key}={val}"')

    # Windows ANSI/OEM for call-able bat snippets under Chinese locale = mbcs/gbk
    payload = "\r\n".join(lines) + ("\r\n" if lines else "")
    dst.write_bytes(payload.encode("mbcs", errors="replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
