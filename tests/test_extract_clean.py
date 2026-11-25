# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / "tools" / ".claude" / "skills" / "doc-read" / "scripts" / "extract_docs.py"


def _load():
    spec = importlib.util.spec_from_file_location("extract_docs", EXTRACT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_docs"] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load()


def test_stem_and_paths(tmp_path: Path):
    src = tmp_path / "某篇.pdf"
    src.write_bytes(b"%")
    assert ex.stem_of(src) == "某篇"
    paths = ex.paths_for(src)
    assert paths["raw"].name == "某篇.raw.txt"
    assert paths["raw"].parent.name == "_extract"


def test_clean_text_strips_nav_noise():
    raw = "=====PAGE 1=====\n首页\n正文第一句。\n更多\n正文第二句。\n"
    cleaned = ex.clean_text(raw, source_format="pdf-text")
    assert "首页" not in cleaned
    assert "正文第一句" in cleaned


def test_is_probably_scan_emptyish():
    assert ex.is_probably_scan("\n\n", 10) is True
    meat = "这是一段足够长的可抽取正文，用来避免被判成扫描件。" * 20
    assert ex.is_probably_scan(meat, 2) is False


def test_password_candidates_include_defaults(monkeypatch):
    monkeypatch.delenv("DOC_READ_PASSWORDS", raising=False)
    monkeypatch.setattr(ex, "_load_secret_passwords", lambda: [])
    cands = ex.password_candidates(["extra"])
    assert cands[0] is None
    assert "extra" in cands
    for p in ex.DEFAULT_PASSWORDS:
        assert p in cands
