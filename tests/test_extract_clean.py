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


def test_scan_plan_by_length():
    assert ex.scan_render_plan(12, ocr_all=False) == ("full", None)
    mode, pages = ex.scan_render_plan(45, ocr_all=False)
    assert mode == "sample"
    assert pages[:5] == [1, 2, 3, 4, 5]
    assert 20 in pages and 40 in pages and 45 not in pages
    mode, pages = ex.scan_render_plan(130, ocr_all=False)
    assert mode == "skip" and pages == [1, 2, 3]
    # Explicit full OCR ignores the page cap.
    assert ex.scan_render_plan(130, ocr_all=True) == ("full", None)


def test_text_pdf_reading_policy():
    assert ex.classify_text_pdf(12, 8000) == ("article", "summary")
    assert ex.classify_text_pdf(60, 60_000) == ("long", "summary")
    assert ex.classify_text_pdf(90, 20_000) == ("book", "index-only")
    assert ex.classify_text_pdf(30, 90_000) == ("book", "index-only")


def test_password_candidates_include_defaults(monkeypatch):
    monkeypatch.delenv("DOC_READ_PASSWORDS", raising=False)
    monkeypatch.setattr(ex, "_load_secret_passwords", lambda: [])
    cands = ex.password_candidates(["extra"])
    assert cands[0] is None
    assert "extra" in cands
    for p in ex.DEFAULT_PASSWORDS:
        assert p in cands


def _shell_link(local_path: str) -> bytes:
    """Minimal .lnk whose LinkInfo local path is ``local_path`` (mbcs)."""
    encoded = local_path.encode("mbcs") + b"\x00"
    # HeaderSize at 0, LinkFlags (HasLinkInfo) at 0x14, total 0x4C bytes.
    header = bytearray(0x4C)
    header[0:4] = (0x4C).to_bytes(4, "little")
    header[0x14:0x18] = (0x02).to_bytes(4, "little")
    # LinkInfo without the optional unicode fields: 24-byte header.
    local_off = 24
    info = b"".join(
        [
            (local_off + len(encoded)).to_bytes(4, "little"),
            local_off.to_bytes(4, "little"),
            (0x01).to_bytes(4, "little"),
            (0).to_bytes(4, "little"),
            local_off.to_bytes(4, "little"),
            (0).to_bytes(4, "little"),
            encoded,
        ]
    )
    return header + info


def test_tool_from_env_file_dir_and_missing(tmp_path, monkeypatch):
    exe = tmp_path / "UnRAR.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv("DOC_READ_UNRAR", str(exe))
    assert ex._tool_from_env("DOC_READ_UNRAR", ("UnRAR.exe",)) == (str(exe), "ok")
    monkeypatch.setenv("DOC_READ_UNRAR", str(tmp_path))
    assert ex._tool_from_env("DOC_READ_UNRAR", ("UnRAR.exe",)) == (str(exe), "ok")
    monkeypatch.setenv("DOC_READ_UNRAR", str(tmp_path / "missing.exe"))
    resolved, status = ex._tool_from_env("DOC_READ_UNRAR", ("UnRAR.exe",))
    assert resolved is None and status == "missing"
    monkeypatch.delenv("DOC_READ_UNRAR")
    assert ex._tool_from_env("DOC_READ_UNRAR", ("UnRAR.exe",))[1] == "unset"


def test_find_unrar_prefers_configured_path(tmp_path, monkeypatch):
    exe = tmp_path / "custom" / "UnRAR.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"MZ")
    monkeypatch.setenv("DOC_READ_UNRAR", str(exe.parent))
    monkeypatch.setattr(ex.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ex, "_winrar_from_start_menu", lambda: [])
    assert ex.find_unrar() == str(exe)


def test_archive_check_fails_when_configured_path_missing(tmp_path, monkeypatch):
    missing = tmp_path / "no-such" / "UnRAR.exe"
    monkeypatch.setenv("DOC_READ_UNRAR", str(missing))
    name, ok, detail = ex._archive_tool_row(
        "UnRAR",
        "DOC_READ_UNRAR",
        ("UnRAR.exe",),
        ex.find_unrar,
        "not found",
    )
    assert name == "UnRAR" and ok is False
    assert "not found" in detail


def test_lnk_local_path_reads_linkinfo():
    blob = _shell_link(r"D:\soft\tools\winrar\WinRAR.exe")
    assert ex._lnk_local_path(blob) == r"D:\soft\tools\winrar\WinRAR.exe"
    assert ex._lnk_local_path(b"not a link") is None


def test_winrar_from_start_menu_uses_shortcut_target(tmp_path, monkeypatch):
    install = tmp_path / "soft" / "tools" / "winrar"
    install.mkdir(parents=True)
    (install / "UnRAR.exe").write_bytes(b"MZ")
    programs = tmp_path / "Programs" / "WinRAR"
    programs.mkdir(parents=True)
    target = install / "WinRAR.exe"
    (programs / "WinRAR.lnk").write_bytes(_shell_link(str(target)))
    (programs / "notes.lnk").write_bytes(_shell_link(str(tmp_path / "other" / "readme.txt")))
    monkeypatch.setattr(
        ex,
        "_start_menu_roots",
        lambda: [tmp_path / "Programs"],
    )
    found = ex._winrar_from_start_menu()
    assert found == [install]
