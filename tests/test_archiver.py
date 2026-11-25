# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVER = ROOT / "tools" / "paid_doc_archiver"
sys.path.insert(0, str(ARCHIVER))

import paid_doc_archiver as pda  # noqa: E402


def test_classify_category_prefers_longer_token():
    tokens = ["龙博认知局内容总结", "付费文", "付"]
    assert pda.classify_category("今日付费文汇总.pdf", tokens) == pda.CATEGORY_PAID
    assert pda.classify_category("普通研报.pdf", tokens) == pda.CATEGORY_UNTRACKED


def test_split_day_key_and_folder(tmp_path: Path):
    month, dd = pda.split_day_key("2026-11-19")
    assert (month, dd) == ("2026-11", "19")
    assert pda.day_folder(tmp_path, "2026-11-19") == tmp_path / "2026-11" / "19"
    with pytest.raises(ValueError):
        pda.split_day_key("2026-11")


def test_safe_move_identical_removes_source(tmp_path: Path):
    import logging

    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()
    src = src_dir / "a.txt"
    dest = dest_dir / "a.txt"
    src.write_text("same", encoding="utf-8")
    dest.write_text("same", encoding="utf-8")
    logger = logging.getLogger("t")
    logger.addHandler(logging.NullHandler())
    result = pda.safe_move(src, dest_dir, set(), logger)
    assert result == "identical_removed"
    assert not src.exists()
    assert dest.read_text(encoding="utf-8") == "same"


def test_safe_move_conflict_renames(tmp_path: Path):
    import logging

    src_dir = tmp_path / "src"
    dest_dir = tmp_path / "dest"
    src_dir.mkdir()
    dest_dir.mkdir()
    src = src_dir / "a.txt"
    (dest_dir / "a.txt").write_text("old", encoding="utf-8")
    src.write_text("new", encoding="utf-8")
    logger = logging.getLogger("t2")
    logger.addHandler(logging.NullHandler())
    result = pda.safe_move(src, dest_dir, set(), logger)
    assert result == "moved"
    assert (dest_dir / "a (1).txt").read_text(encoding="utf-8") == "new"


def test_archive_daily_writes_month_day_layout(tmp_path: Path):
    import logging
    import os
    import time

    src = tmp_path / "wechat" / "2026-11"
    out = tmp_path / "local"
    src.mkdir(parents=True)
    f = src / "思投社早报.pdf"
    f.write_bytes(b"pdf")
    # Force mtime to 2026-11-19 local — use a fixed timestamp if possible; else accept today.
    # For stability, monkeypatch day_key_from_mtime.
    logger = logging.getLogger("arch")
    logger.addHandler(logging.NullHandler())
    tokens = ["思投社"]

    original = pda.day_key_from_mtime
    pda.day_key_from_mtime = lambda path: "2026-11-19"  # type: ignore
    try:
        moved, identical, failed, total = pda.archive_daily(src, out, tokens, False, logger)
    finally:
        pda.day_key_from_mtime = original  # type: ignore
    assert (moved, identical, failed, total) == (1, 0, 0, 1)
    assert (out / "2026-11" / "19" / "付费文" / "思投社早报.pdf").is_file()
