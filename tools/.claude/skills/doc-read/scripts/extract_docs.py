#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""doc-read one-shot local extractor.

Writes beside each source file:
  _extract/<stem>.raw.txt
  _extract/<stem>.clean.md
  _extract/<stem>.meta.json
  _extract/<stem>.transcript.txt   (audio only)
  _extract/imgs/<stem>_pN.png      (scan PDFs / --render-pages)

Designed to run inside the project-local env:
  YOUR_DOC_ROOT/.conda/doc-read

Usage examples:
  python extract_docs.py path/to/file.pdf
  python extract_docs.py path/to/dir --glob "*.pdf"
  python extract_docs.py path/to/dir --force
  python extract_docs.py scan.pdf --ocr
  python extract_docs.py talk.mp3 --asr
  python extract_docs.py packed.zip
  python extract_docs.py secret.pdf --password extra
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Optional

AUDIO_EXT = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}
DOC_EXT = {".docx"}
PDF_EXT = {".pdf"}
OLD_DOC_EXT = {".doc"}
ARCHIVE_EXT = {".zip", ".rar", ".7z"}

# Library-local archive/PDF passwords (try in order after empty).
# Keep in sync with SKILL.md 「有密码的压缩包 / 加密 PDF」.
# Extra passwords: secrets.local.json / DOC_READ_PASSWORDS env (comma-separated).
DEFAULT_PASSWORDS: list[str] = [
    "36903690",
    "931226",
]

_MUPDF_NOISE_RE = re.compile(
    r"^\s*(MuPDF error:|warning:\s*MuPDF|mupdf:\s*)",
    re.IGNORECASE,
)


class _FilteredStderr:
    """Drop chatty MuPDF xref warnings while keeping real errors visible."""

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self._buf = ""

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._buf += s
        written = 0
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if _MUPDF_NOISE_RE.search(line):
                written += len(line) + 1
                continue
            out = line + "\n"
            self._wrapped.write(out)
            written += len(out)
        return written

    def flush(self) -> None:
        if self._buf and not _MUPDF_NOISE_RE.search(self._buf):
            self._wrapped.write(self._buf)
        self._buf = ""
        self._wrapped.flush()

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


@contextlib.contextmanager
def quiet_mupdf() -> Iterator[None]:
    """Silence MuPDF C chatter on stdout/stderr fds during PDF work."""
    old_py_err = sys.stderr
    sys.stderr = _FilteredStderr(old_py_err)
    # Also filter Python-level stdout in case bindings print there.
    old_py_out = sys.stdout
    sys.stdout = _FilteredStderr(old_py_out)

    devnull = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    saved_fds: list[tuple[int, int]] = []
    for stream in (sys.__stdout__, sys.__stderr__):
        try:
            fd = stream.fileno()
        except Exception:
            continue
        try:
            kept = os.dup(fd)
        except OSError:
            continue
        saved_fds.append((fd, kept))
        try:
            os.dup2(devnull.fileno(), fd)
        except OSError:
            os.close(kept)
            saved_fds.pop()
    try:
        yield
    finally:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:
                pass
        for fd, kept in reversed(saved_fds):
            try:
                os.dup2(kept, fd)
            finally:
                os.close(kept)
        devnull.close()
        sys.stdout = old_py_out
        sys.stderr = old_py_err


def _repo_root_guess() -> Path:
    """Best-effort repo root from this file (tools/.../scripts or .claude/.../scripts)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "tools").is_dir() and (parent / ".claude").is_dir():
            return parent
        if (parent / "local").is_dir() and (parent / ".git").exists():
            return parent
    # tools/.claude/skills/doc-read/scripts -> parents[5] == repo
    return here.parents[5] if len(here.parents) > 5 else here.parents[-1]


def _load_secret_passwords() -> list[str]:
    out: list[str] = []
    env = os.environ.get("DOC_READ_PASSWORDS", "").strip()
    if env:
        out.extend(p.strip() for p in env.split(",") if p.strip())
    secrets = Path(os.environ.get("DOC_READ_SECRETS", "") or (_repo_root_guess() / "secrets.local.json"))
    if secrets.is_file():
        try:
            data = json.loads(secrets.read_text(encoding="utf-8"))
            pwds = data.get("passwords", []) if isinstance(data, dict) else data
            if isinstance(pwds, list):
                out.extend(str(p).strip() for p in pwds if str(p).strip())
        except (OSError, json.JSONDecodeError):
            pass
    return out

NAV_NOISE_RE = re.compile(
    r"^("
    r"更多|科技|地产|汽车|消费|能源|健康|环科|民生|ESG|数字说|比较|中国改革|专题|讣闻|"
    r"政经\s*>|首页|经济|金融|公司|政经|世界|观点|博客|图片|视频|English|"
    r"商城|订阅|退出|数据|我闻|机构订阅|会议|Promotion|应用下载|帮助|"
    r"网上有害信息举报专区|相关报道|请输入要搜索的信息|电邮"
    r")",
    re.IGNORECASE,
)
PAGE_MARK_RE = re.compile(r"^=====PAGE\s+\d+=====\s*$")
META_HEADER_RE = re.compile(r"^#\s*(language=|duration=)", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"[ \t]+\n")
MULTI_BLANK_RE = re.compile(r"\n{3,}")
SENTENCE_END_RE = re.compile(r"[。！？!?；;]$")

# High-confidence ASR fixes only — keep conservative.
ASR_FIXES: list[tuple[str, str]] = [
    ("客创50", "科创50"),
    ("客创 50", "科创50"),
    ("次代危机", "次贷危机"),
    ("法令枪", "发令枪"),
    ("下错", "下挫"),
    ("细底花拉", "稀里哗啦"),
    ("权力救市", "全力救市"),
    ("权力稳定", "全力稳定"),
    ("入不出出", "入不敷出"),
    ("入不复出", "入不敷出"),
    ("清黄不接", "青黄不接"),
    ("回彻", "回撤"),
    ("极功尽力", "急功近利"),
    ("成压", "承压"),
    ("注底", "筑底"),
    ("净若寒蝉", "噤若寒蝉"),
    ("压仓史", "压舱石"),
    ("现金流转幅", "现金流转负"),
    ("被坚强", "被清盘"),
]

AUDIO_BOILERPLATE_RE = re.compile(
    r"^("
    r"每天\s*10\s*分钟.*|"
    r"拆解新闻背后的逻辑.*|"
    r"插解新闻背后的逻辑.*|"
    r"大家好[,，].*|"
    r"我是东小姐.*|"
    r"个人观点.*不构成.*|"
    r"仅供参观.*|"
    r"仅供参考.*|"
    r"好了[，,]?\s*今天(我们)?就到这.*|"
    r"今天(我们)?就到这(个地方|里).*|"
    r"以上就是我们今天聊到的所有的内容.*|"
    r"感谢收听.*|"
    r"我们下期再见.*"
    r")$"
)


@dataclass
class ExtractResult:
    source: str
    title: str = ""
    author: str = ""
    date: str = ""
    format: str = ""  # pdf-text|pdf-scan|docx|audio|unsupported
    tags: list = field(default_factory=list)
    one_liner: str = ""
    worth_deep_read: Optional[bool] = None
    key_conclusions: list = field(default_factory=list)
    extracted_at: str = ""
    summary_path: str = ""
    raw_path: str = ""
    clean_path: str = ""
    transcript_path: str = ""
    page_count: int = 0
    char_count: int = 0
    status: str = "ok"  # ok|skipped|error|needs_ocr|needs_asr|needs_password
    message: str = ""
    deps_missing: list = field(default_factory=list)
    password_used: str = ""  # "" | "(none)" | working password


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stem_of(path: Path) -> str:
    return path.stem


def extract_dir_for(source: Path) -> Path:
    return source.parent / "_extract"


def paths_for(source: Path) -> dict[str, Path]:
    stem = stem_of(source)
    base = extract_dir_for(source)
    return {
        "base": base,
        "raw": base / f"{stem}.raw.txt",
        "clean": base / f"{stem}.clean.md",
        "meta": base / f"{stem}.meta.json",
        "summary": base / f"{stem}.summary.md",
        "transcript": base / f"{stem}.transcript.txt",
        "imgs": base / "imgs",
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_existing_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def merge_meta(existing: dict, result: ExtractResult) -> dict:
    data = asdict(result)
    # Preserve human-filled fields when re-extracting.
    for key in ("tags", "one_liner", "worth_deep_read", "key_conclusions", "author", "date", "title"):
        old = existing.get(key)
        if key == "title":
            if existing.get("title") and not result.title:
                data["title"] = existing["title"]
            continue
        if key in ("author", "date") and existing.get(key) and not result.__dict__.get(key):
            data[key] = existing[key]
            continue
        if key == "tags" and existing.get("tags"):
            data["tags"] = existing["tags"]
            continue
        if key == "one_liner" and existing.get("one_liner"):
            data["one_liner"] = existing["one_liner"]
            continue
        if key == "worth_deep_read" and existing.get("worth_deep_read") is not None:
            data["worth_deep_read"] = existing["worth_deep_read"]
            continue
        if key == "key_conclusions" and existing.get("key_conclusions"):
            data["key_conclusions"] = existing["key_conclusions"]
            continue
        _ = old
    return data


def guess_title(source: Path, text: str) -> str:
    name = source.stem
    # Strip common trailing copy markers like (1)
    name = re.sub(r"\(\d+\)$", "", name).strip()
    if name:
        return name
    for line in text.splitlines():
        s = line.strip()
        if s and not PAGE_MARK_RE.match(s) and len(s) <= 80:
            return s
    return source.name


def apply_asr_fixes(text: str) -> str:
    for old, new in ASR_FIXES:
        if old != new:
            text = text.replace(old, new)
    return text


def merge_short_lines(lines: list[str], max_joined_chars: int = 180) -> list[str]:
    """Merge fragmented ASR lines into denser paragraphs."""
    out: list[str] = []
    buf = ""
    for line in lines:
        s = line.strip()
        if not s:
            if buf:
                out.append(buf)
                buf = ""
            if out and out[-1] != "":
                out.append("")
            continue
        if META_HEADER_RE.match(s) or s.startswith("<!-- =====PAGE"):
            if buf:
                out.append(buf)
                buf = ""
            out.append(s)
            continue
        if not buf:
            buf = s
            continue
        # Prefer starting a new paragraph after sentence end + capitalized/new topic length.
        if SENTENCE_END_RE.search(buf) and (len(buf) >= 40 or len(s) >= 28):
            out.append(buf)
            buf = s
            continue
        candidate = f"{buf}{s}" if buf.endswith(("，", ",", "、", ":", "：", "的", "了", "着", "过")) else f"{buf}{s}"
        # Join short fragments; start new paragraph after a clear sentence end.
        if len(buf) < 24 or (not SENTENCE_END_RE.search(buf) and len(candidate) <= max_joined_chars):
            buf = candidate
        elif SENTENCE_END_RE.search(buf) and len(buf) >= 36:
            out.append(buf)
            buf = s
        elif len(candidate) <= max_joined_chars:
            buf = candidate
        else:
            out.append(buf)
            buf = s
    if buf:
        out.append(buf)
    # Collapse excessive blank lines
    compact: list[str] = []
    for line in out:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    return compact


def clean_text(raw: str, *, source_format: str = "") -> str:
    lines: list[str] = []
    fmt = (source_format or "").lower()
    is_audio = fmt == "audio" or raw.lstrip().startswith("# language=")

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if PAGE_MARK_RE.match(s):
            lines.append("")
            lines.append(f"<!-- {s} -->")
            lines.append("")
            continue
        if META_HEADER_RE.match(s):
            # Keep one compact machine header for audio, but it stays out of prose density.
            lines.append(s)
            continue
        if NAV_NOISE_RE.match(s) and len(s) <= 80:
            continue
        if is_audio and AUDIO_BOILERPLATE_RE.match(s):
            continue
        lines.append(s)

    if is_audio:
        lines = merge_short_lines(lines)

    text = "\n".join(lines)
    if is_audio:
        text = apply_asr_fixes(text)
    text = WHITESPACE_RE.sub("\n", text)
    text = MULTI_BLANK_RE.sub("\n\n", text).strip()
    return text + ("\n" if text else "")


def is_probably_scan(text: str, page_count: int) -> bool:
    # Count non-space CJK/latin chars.
    meaningful = re.sub(r"\s+", "", text)
    # Remove page markers from consideration.
    meaningful = PAGE_MARK_RE.sub("", meaningful)
    chars = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", meaningful))
    if page_count <= 0:
        page_count = 1
    per_page = chars / page_count
    return chars < 80 or per_page < 40


def password_candidates(extra: Optional[Iterable[str]] = None) -> list[Optional[str]]:
    """Empty first (unencrypted), then library defaults, secrets/env, then extras."""
    seen: set[str] = set()
    out: list[Optional[str]] = [None]
    for pwd in list(DEFAULT_PASSWORDS) + _load_secret_passwords() + list(extra or []):
        if not pwd or pwd in seen:
            continue
        seen.add(pwd)
        out.append(pwd)
    return out


def _pwd_label(pwd: Optional[str]) -> str:
    return "(none)" if pwd is None else pwd


def find_7z() -> Optional[str]:
    for candidate in (
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\7-Zip\7z.exe"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def find_unrar() -> Optional[str]:
    """Locate WinRAR's UnRAR.exe (rar only; does not unpack .7z)."""
    for candidate in (
        shutil.which("UnRAR"),
        shutil.which("unrar"),
        r"C:\Program Files\WinRAR\UnRAR.exe",
        r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\WinRAR\UnRAR.exe"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _clear_dir(dest_dir: Path) -> None:
    if not dest_dir.exists():
        return
    for child in dest_dir.iterdir():
        if child.is_file():
            child.unlink(missing_ok=True)
        else:
            shutil.rmtree(child, ignore_errors=True)


def _run_unrar(
    unrar: str,
    source: Path,
    dest_dir: Path,
    candidates: list[Optional[str]],
) -> tuple[list[Path], str]:
    """Try UnRAR with password candidates. Raises NeedsPassword/RuntimeError."""
    last_err = ""
    dest_dir.mkdir(parents=True, exist_ok=True)
    # UnRAR wants trailing sep on destination so it extracts into the folder.
    dest_arg = str(dest_dir) + os.sep
    for pwd in candidates:
        _clear_dir(dest_dir)
        cmd = [
            unrar,
            "x",
            "-y",
            f"-p{'' if pwd is None else pwd}",
            str(source),
            dest_arg,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False,
            )
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            continue
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        low = out.lower()
        if proc.returncode == 0:
            files = [p for p in dest_dir.rglob("*") if p.is_file()]
            if files:
                return files, _pwd_label(pwd)
            last_err = "UnRAR ok but no files"
            continue
        if "incorrect password" in low or "wrong password" in low or "password" in low:
            last_err = out.strip()[:200]
            continue
        last_err = out.strip()[:200] or f"UnRAR exit {proc.returncode}"
        if "incorrect password" not in low and "wrong password" not in low:
            break
    raise NeedsPassword(
        f"rar encrypted or unreadable via UnRAR; tried {len(candidates)} password(s); last={last_err}"
    )


class NeedsPassword(RuntimeError):
    """Raised when all known passwords fail on an encrypted file."""


def extract_pdf_text(source: Path, passwords: Optional[Iterable[str]] = None) -> tuple[str, int, str, str]:
    """Return (raw_text, page_count, engine, password_used_label). Prefer pymupdf, fall back to pypdf."""
    errors: list[str] = []
    candidates = password_candidates(passwords)

    try:
        import pymupdf  # type: ignore

        last_auth_err = ""
        with quiet_mupdf():
            for pwd in candidates:
                doc = pymupdf.open(source)
                try:
                    if doc.is_encrypted:
                        # authenticate returns >0 on success; password may still be needed even if empty works for some.
                        ok = doc.authenticate("" if pwd is None else pwd)
                        if not ok:
                            last_auth_err = "authenticate failed"
                            doc.close()
                            continue
                    parts: list[str] = []
                    for i, page in enumerate(doc, start=1):
                        parts.append(f"=====PAGE {i}=====")
                        parts.append(page.get_text("text") or "")
                    page_count = doc.page_count
                    label = _pwd_label(pwd)
                    doc.close()
                    return "\n".join(parts).strip() + "\n", page_count, "pymupdf", label
                except Exception as e:  # noqa: BLE001
                    last_auth_err = str(e)
                    try:
                        doc.close()
                    except Exception:
                        pass
        if last_auth_err:
            raise NeedsPassword(f"PDF encrypted; tried {len(candidates)} password(s)")
        errors.append(f"pymupdf: {last_auth_err or 'open failed'}")
    except NeedsPassword:
        raise
    except Exception as e:  # noqa: BLE001
        errors.append(f"pymupdf: {e}")

    try:
        from pypdf import PdfReader  # type: ignore

        last_auth_err = ""
        for pwd in candidates:
            try:
                reader = PdfReader(str(source))
                if reader.is_encrypted:
                    code = reader.decrypt("" if pwd is None else pwd)
                    # pypdf: 0 = fail, 1/2 = success
                    if not code:
                        last_auth_err = "decrypt failed"
                        continue
                parts = []
                for i, page in enumerate(reader.pages, start=1):
                    parts.append(f"=====PAGE {i}=====")
                    parts.append(page.extract_text() or "")
                return "\n".join(parts).strip() + "\n", len(reader.pages), "pypdf", _pwd_label(pwd)
            except Exception as e:  # noqa: BLE001
                last_auth_err = str(e)
                continue
        raise NeedsPassword(f"PDF encrypted; tried {len(candidates)} password(s); last={last_auth_err}")
    except NeedsPassword:
        raise
    except Exception as e:  # noqa: BLE001
        errors.append(f"pypdf: {e}")

    raise RuntimeError("; ".join(errors) or "PDF text extraction failed")


def render_pdf_pages(
    source: Path,
    imgs_dir: Path,
    stem: str,
    max_pages: int = 0,
    dpi: int = 150,
    password: Optional[str] = None,
) -> list[Path]:
    import pymupdf  # type: ignore

    imgs_dir.mkdir(parents=True, exist_ok=True)
    with quiet_mupdf():
        doc = pymupdf.open(source)
        if doc.is_encrypted:
            # password_used label "(none)" means empty string already worked upstream.
            extras: list[str] = []
            prefer: list[Optional[str]]
            if password == "(none)":
                prefer = [None]
            elif password:
                prefer = [password]
                extras = [password]
            else:
                prefer = []
            ok = False
            ordered = prefer + [p for p in password_candidates(extras) if p not in prefer]
            for pwd in ordered:
                if doc.authenticate("" if pwd is None else pwd):
                    ok = True
                    break
            if not ok:
                doc.close()
                raise NeedsPassword("PDF encrypted; cannot render pages")
        out: list[Path] = []
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        limit = doc.page_count if max_pages <= 0 else min(doc.page_count, max_pages)
        for i in range(limit):
            page = doc[i]
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            target = imgs_dir / f"{stem}_p{i + 1}.png"
            pix.save(str(target))
            out.append(target)
        doc.close()
    return out


def unpack_archive(
    source: Path,
    dest_dir: Path,
    passwords: Optional[Iterable[str]] = None,
) -> tuple[list[Path], str]:
    """Unpack archive into dest_dir. Returns (extracted_files, password_used_label)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    ext = source.suffix.lower()
    candidates = password_candidates(passwords)
    last_err = ""

    if ext == ".zip":
        for pwd in candidates:
            try:
                with zipfile.ZipFile(source) as zf:
                    # Detect encryption without extracting.
                    encrypted = any(info.flag_bits & 0x1 for info in zf.infolist())
                    pwd_bytes = None if pwd is None else pwd.encode("utf-8")
                    if encrypted and pwd is None:
                        # Still try empty; some tools mark flag oddly.
                        pass
                    try:
                        zf.extractall(dest_dir, pwd=pwd_bytes)
                    except RuntimeError as e:
                        # Wrong password typically raises RuntimeError: Bad password
                        last_err = str(e)
                        if "password" in last_err.lower() or "Bad password" in last_err:
                            continue
                        raise
                    files = [p for p in dest_dir.rglob("*") if p.is_file()]
                    if not files and encrypted:
                        last_err = "extract produced no files"
                        continue
                    return files, _pwd_label(pwd)
            except zipfile.BadZipFile as e:
                last_err = str(e)
                break
            except NeedsPassword:
                raise
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                if "password" in str(e).lower():
                    continue
                break
        raise NeedsPassword(f"zip encrypted or unreadable; tried {len(candidates)} password(s); last={last_err}")

    # .rar / .7z: prefer 7-Zip; .rar falls back to WinRAR UnRAR when 7z is absent/fails.
    seven = find_7z()
    seven_last_err = ""
    seven_passwordish = False
    if seven:
        for pwd in candidates:
            _clear_dir(dest_dir)
            cmd = [seven, "x", "-y", f"-o{dest_dir}", str(source)]
            # -p with empty is "no password" for 7z; always pass to avoid interactive prompt.
            cmd.insert(2, f"-p{'' if pwd is None else pwd}")
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    check=False,
                )
            except Exception as e:  # noqa: BLE001
                seven_last_err = str(e)
                continue
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            low = out.lower()
            if proc.returncode == 0:
                files = [p for p in dest_dir.rglob("*") if p.is_file()]
                if files:
                    return files, _pwd_label(pwd)
                seven_last_err = "7z ok but no files"
                continue
            if "wrong password" in low or "cannot open encrypted" in low or "password" in low:
                seven_passwordish = True
                seven_last_err = out.strip()[:200]
                continue
            seven_last_err = out.strip()[:200] or f"7z exit {proc.returncode}"
            # Non-password failure: stop retrying passwords with 7z.
            if "wrong password" not in low:
                break
        if seven_passwordish:
            # All password candidates failed under 7z — no point switching tools.
            raise NeedsPassword(
                f"archive encrypted or unreadable; tried {len(candidates)} password(s); last={seven_last_err}"
            )

    if ext == ".rar":
        unrar = find_unrar()
        if unrar:
            return _run_unrar(unrar, source, dest_dir, candidates)
        if not seven:
            raise RuntimeError(
                "no unpacker for .rar; install 7-Zip or WinRAR "
                "(UnRAR searched on PATH and common Program Files locations)"
            )
        raise RuntimeError(f"7z failed for .rar and UnRAR missing; last={seven_last_err}")

    if not seven:
        raise RuntimeError(
            f"no unpacker for {ext}; install 7-Zip (UnRAR cannot open .7z)"
        )
    raise NeedsPassword(
        f"archive encrypted or unreadable; tried {len(candidates)} password(s); last={seven_last_err or last_err}"
    )


def ocr_images(image_paths: Iterable[Path]) -> tuple[str, list[str]]:
    """OCR page images. Returns (text, missing_deps)."""
    missing: list[str] = []
    parts: list[str] = []

    # Prefer rapidocr if present (lighter); then pytesseract; then easyocr.
    engine = None
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        engine = ("rapidocr", RapidOCR())
    except Exception:
        pass

    if engine is None:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            engine = ("pytesseract", (pytesseract, Image))
        except Exception:
            pass

    if engine is None:
        try:
            import easyocr  # type: ignore

            engine = ("easyocr", easyocr.Reader(["ch_sim", "en"], verbose=False))
        except Exception:
            missing.append("rapidocr-onnxruntime|pytesseract+Pillow|easyocr")
            return "", missing

    name, obj = engine
    for idx, img in enumerate(image_paths, start=1):
        parts.append(f"=====PAGE {idx}=====")
        try:
            if name == "rapidocr":
                result, _ = obj(str(img))
                lines = [item[1] for item in (result or []) if len(item) >= 2]
                parts.append("\n".join(lines))
            elif name == "pytesseract":
                pytesseract, Image = obj
                text = pytesseract.image_to_string(Image.open(img), lang="chi_sim+eng")
                parts.append(text or "")
            else:  # easyocr
                result = obj.readtext(str(img), detail=0)
                parts.append("\n".join(result or []))
        except Exception as e:  # noqa: BLE001
            parts.append(f"[OCR_ERROR page={idx} engine={name}] {e}")
    return "\n".join(parts).strip() + "\n", missing


def extract_docx(source: Path) -> tuple[str, int]:
    import docx  # type: ignore

    document = docx.Document(str(source))
    paras = [p.text.strip() for p in document.paragraphs]
    text = "\n".join([p for p in paras if p is not None]).strip() + "\n"
    # page_count unknown for docx; use 0
    return text, 0


def ensure_local_cuda_dlls() -> bool:
    """Make local conda CUDA DLLs (cublas etc.) importable on Windows."""
    candidates: list[Path] = []
    py = os.environ.get("DOC_READ_PYTHON")
    if py:
        # .../python.exe -> env root / Library / bin
        candidates.append(Path(py).resolve().parent / "Library" / "bin")
    root = os.environ.get("DOC_READ_ROOT") or str(_repo_root_guess())
    candidates.append(Path(root) / ".conda" / "doc-read" / "Library" / "bin")
    # Relative to synced skill under <repo>/.claude/.../scripts -> repo/.conda
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / ".conda" / "doc-read" / "Library" / "bin")
    seen: set[Path] = set()
    for bin_dir in candidates:
        try:
            bin_dir = bin_dir.resolve()
        except OSError:
            continue
        if bin_dir in seen:
            continue
        seen.add(bin_dir)
        dll = bin_dir / "cublas64_12.dll"
        if not dll.exists():
            continue
        os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(str(bin_dir))
        except Exception:
            pass
        return True
    return False


def resolve_asr_device(device: str) -> tuple[str, str]:
    """Return (device, compute_type). auto prefers CUDA when available."""
    device = (device or "auto").lower()
    if device == "cpu":
        return "cpu", "int8"
    if device in {"cuda", "gpu", "auto"}:
        ensure_local_cuda_dlls()
        try:
            import ctranslate2  # type: ignore

            types = set(ctranslate2.get_supported_compute_types("cuda"))
            if "float16" in types:
                return "cuda", "float16"
            if "int8_float16" in types:
                return "cuda", "int8_float16"
            return "cuda", "float32"
        except Exception:
            if device != "auto":
                raise
            return "cpu", "int8"
    raise ValueError(f"unsupported --device: {device}")


def extract_audio(source: Path, device: str = "auto") -> tuple[str, list[str], str]:
    missing: list[str] = []
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        missing.append("faster-whisper")
        return "", missing, ""

    try:
        asr_device, compute_type = resolve_asr_device(device)
    except Exception as e:  # noqa: BLE001
        return "", [f"asr-device:{e}"], ""

    model = WhisperModel("small", device=asr_device, compute_type=compute_type)
    segments, info = model.transcribe(str(source), language="zh", vad_filter=True)
    lines = [f"# language={getattr(info, 'language', '')} duration={getattr(info, 'duration', '')} device={asr_device}/{compute_type}"]
    for seg in segments:
        lines.append(seg.text.strip())
    note = f"device={asr_device}/{compute_type}"
    return "\n".join([x for x in lines if x]).strip() + "\n", missing, note


def process_one(
    source: Path,
    *,
    force: bool = False,
    ocr: bool = False,
    asr: bool = False,
    render_pages: bool = False,
    max_render_pages: int = 0,
    dpi: int = 150,
    device: str = "auto",
    passwords: Optional[Iterable[str]] = None,
) -> ExtractResult:
    source = source.resolve()
    outs = paths_for(source)
    result = ExtractResult(
        source=str(source),
        extracted_at=utc_now_iso(),
        summary_path=str(outs["summary"]),
        raw_path=str(outs["raw"]),
        clean_path=str(outs["clean"]),
    )
    extra_passwords = [p for p in (passwords or []) if p]

    if not source.exists():
        result.status = "error"
        result.message = "source not found"
        return result

    existing_meta = load_existing_meta(outs["meta"])
    if outs["raw"].exists() and outs["raw"].stat().st_size > 0 and not force:
        raw = outs["raw"].read_text(encoding="utf-8", errors="ignore")
        fmt = existing_meta.get("format") or (
            "audio"
            if source.suffix.lower() in AUDIO_EXT
            else "pdf-text"
            if source.suffix.lower() in PDF_EXT
            else "archive"
            if source.suffix.lower() in ARCHIVE_EXT
            else "docx"
        )
        # Always refresh clean from raw so cleaning upgrades apply without full re-extract.
        write_text(outs["clean"], clean_text(raw, source_format=fmt))
        result.title = existing_meta.get("title") or guess_title(source, raw)
        result.format = fmt
        result.password_used = existing_meta.get("password_used") or ""
        if outs["transcript"].exists():
            result.transcript_path = str(outs["transcript"])
        elif existing_meta.get("transcript_path"):
            result.transcript_path = existing_meta["transcript_path"]
        result.char_count = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", raw))
        result.page_count = len(PAGE_MARK_RE.findall(raw))
        result.status = "skipped"
        result.message = "raw exists; refreshed clean; use --force to re-extract"
        meta = merge_meta(existing_meta, result)
        # Keep richer human/summary fields already on disk.
        for keep_key in ("summary_path", "transcript_path", "password_used"):
            if existing_meta.get(keep_key) and not meta.get(keep_key):
                meta[keep_key] = existing_meta[keep_key]
        write_text(outs["meta"], json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        return result

    ext = source.suffix.lower()
    raw = ""
    page_count = 0

    try:
        if ext in ARCHIVE_EXT:
            result.format = "archive"
            unpack_dir = outs["base"] / "_unpacked" / stem_of(source)
            if unpack_dir.exists() and force:
                shutil.rmtree(unpack_dir, ignore_errors=True)
            files, pwd_label = unpack_archive(source, unpack_dir, passwords=extra_passwords)
            result.password_used = pwd_label
            # Only process document-like members; skip nested junk.
            # Members live under `_extract/_unpacked/`, so do NOT exclude by `_extract` here.
            children = [
                f
                for f in files
                if f.suffix.lower() in (PDF_EXT | DOC_EXT | OLD_DOC_EXT | AUDIO_EXT)
            ]
            child_results = [
                process_one(
                    child,
                    force=force,
                    ocr=ocr,
                    asr=asr,
                    render_pages=render_pages,
                    max_render_pages=max_render_pages,
                    dpi=dpi,
                    device=device,
                    passwords=extra_passwords,
                )
                for child in children
            ]
            # If a single document archive, promote its text products to the archive stem
            # so "\u8bfb\u8fd9\u4e2a zip" can follow the normal summary/clean path.
            if len(child_results) == 1 and child_results[0].status in {"ok", "skipped", "needs_ocr", "needs_asr"}:
                child = child_results[0]
                child_raw = Path(child.raw_path)
                if child_raw.exists() and child_raw.stat().st_size > 0:
                    raw = child_raw.read_text(encoding="utf-8", errors="ignore")
                    write_text(outs["raw"], raw)
                    cleaned = clean_text(raw, source_format=child.format)
                    write_text(outs["clean"], cleaned)
                    result.format = child.format
                    result.title = child.title or guess_title(source, cleaned or raw)
                    result.page_count = child.page_count
                    result.char_count = child.char_count
                    result.status = child.status
                    result.deps_missing = child.deps_missing
                    result.message = (
                        f"archive->{Path(child.source).name}; password={pwd_label}; {child.message}"
                    ).strip("; ")
                    if child.transcript_path:
                        result.transcript_path = child.transcript_path
                    meta = merge_meta(existing_meta, result)
                    meta["archive_unpacked_to"] = str(unpack_dir)
                    meta["archive_members"] = [str(c.source) for c in child_results]
                    write_text(outs["meta"], json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
                    return result

            # Multi-member (or empty): keep archive-level meta only; no fake raw.
            result.title = guess_title(source, "")
            parts = [f"unpacked={len(files)}", f"docs={len(children)}", f"password={pwd_label}"]
            if not children:
                result.status = "error"
                parts.append("no pdf/docx/audio members")
            else:
                bad = [c for c in child_results if c.status in {"error", "needs_password"}]
                if bad and len(bad) == len(child_results):
                    result.status = bad[0].status
                else:
                    result.status = "ok"
                parts.append(
                    "children="
                    + ",".join(f"{Path(c.source).name}:{c.status}" for c in child_results)
                )
            result.message = "; ".join(parts)
            meta = merge_meta(existing_meta, result)
            meta["archive_unpacked_to"] = str(unpack_dir)
            meta["archive_members"] = [str(c.source) for c in child_results]
            write_text(outs["meta"], json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
            return result

        if ext in PDF_EXT:
            raw, page_count, engine, pwd_label = extract_pdf_text(source, passwords=extra_passwords)
            result.format = "pdf-text"
            result.password_used = pwd_label
            result.message = f"engine={engine}; password={pwd_label}"
            scan = is_probably_scan(raw, page_count)
            if scan:
                result.format = "pdf-scan"
                # Always materialize page images for scans so OCR can be done later.
                images = render_pdf_pages(
                    source,
                    outs["imgs"],
                    stem_of(source),
                    max_pages=max_render_pages,
                    dpi=dpi,
                    password=pwd_label,
                )
                result.message += f"; rendered={len(images)} pages"
                if ocr:
                    ocr_text, missing = ocr_images(images)
                    if missing:
                        result.status = "needs_ocr"
                        result.deps_missing = missing
                        result.message += f"; OCR deps missing: {', '.join(missing)}"
                    elif ocr_text.strip():
                        raw = ocr_text
                        result.message += "; OCR filled raw"
                    else:
                        result.status = "needs_ocr"
                        result.message += "; OCR returned empty"
                else:
                    result.status = "needs_ocr"
                    result.message += "; scan detected; raw is sparse; rerun with --ocr after installing OCR extras"
            elif render_pages:
                images = render_pdf_pages(
                    source,
                    outs["imgs"],
                    stem_of(source),
                    max_pages=max_render_pages,
                    dpi=dpi,
                    password=pwd_label,
                )
                result.message += f"; rendered={len(images)} pages"

        elif ext in DOC_EXT:
            raw, page_count = extract_docx(source)
            result.format = "docx"
        elif ext in OLD_DOC_EXT:
            result.status = "error"
            result.format = "unsupported"
            result.message = ".doc not supported directly; convert to .docx first"
            write_text(outs["meta"], json.dumps(merge_meta(existing_meta, result), ensure_ascii=False, indent=2) + "\n")
            return result
        elif ext in AUDIO_EXT:
            result.format = "audio"
            if not asr:
                result.status = "needs_asr"
                result.message = "audio detected; rerun with --asr after installing faster-whisper"
                result.deps_missing = ["faster-whisper"]
                write_text(outs["meta"], json.dumps(merge_meta(existing_meta, result), ensure_ascii=False, indent=2) + "\n")
                return result
            transcript, missing, asr_note = extract_audio(source, device=device)
            if missing:
                result.status = "needs_asr"
                result.deps_missing = missing
                result.message = f"ASR deps missing: {', '.join(missing)}"
                write_text(outs["meta"], json.dumps(merge_meta(existing_meta, result), ensure_ascii=False, indent=2) + "\n")
                return result
            write_text(outs["transcript"], transcript)
            raw = transcript
            result.transcript_path = str(outs["transcript"])
            if asr_note:
                result.message = asr_note
        else:
            result.status = "error"
            result.format = "unsupported"
            result.message = f"unsupported extension: {ext}"
            write_text(outs["meta"], json.dumps(merge_meta(existing_meta, result), ensure_ascii=False, indent=2) + "\n")
            return result

        write_text(outs["raw"], raw)
        cleaned = clean_text(raw, source_format=result.format)
        write_text(outs["clean"], cleaned)
        result.title = guess_title(source, cleaned or raw)
        result.page_count = page_count or len(PAGE_MARK_RE.findall(raw))
        result.char_count = len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", raw))
        if result.status == "ok" and result.format == "pdf-scan" and is_probably_scan(raw, result.page_count):
            # keep needs_ocr if still sparse
            if not ocr:
                result.status = "needs_ocr"
        meta = merge_meta(existing_meta, result)
        write_text(outs["meta"], json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
        return result
    except NeedsPassword as e:
        result.status = "needs_password"
        result.message = str(e)
        write_text(outs["meta"], json.dumps(merge_meta(existing_meta, result), ensure_ascii=False, indent=2) + "\n")
        return result
    except Exception as e:  # noqa: BLE001
        result.status = "error"
        result.message = str(e)
        write_text(outs["meta"], json.dumps(merge_meta(existing_meta, result), ensure_ascii=False, indent=2) + "\n")
        return result


def iter_sources(paths: list[Path], pattern: str | None) -> list[Path]:
    found: list[Path] = []
    for p in paths:
        if p.is_file():
            found.append(p)
        elif p.is_dir():
            glob = pattern or "*"
            for child in sorted(p.rglob(glob)):
                if child.is_file() and child.suffix.lower() in (PDF_EXT | DOC_EXT | OLD_DOC_EXT | AUDIO_EXT | ARCHIVE_EXT):
                    # skip outputs inside _extract
                    if "_extract" in child.parts:
                        continue
                    found.append(child)
        else:
            print(f"[warn] missing path: {p}", file=sys.stderr)
    # de-dup preserve order
    seen = set()
    out = []
    for f in found:
        rp = str(f.resolve())
        if rp not in seen:
            seen.add(rp)
            out.append(f)
    return out


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds + 0.5), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def safe_print(*args, file=None, **kwargs) -> None:
    """print that won't crash on Windows GBK consoles with rare Unicode names."""
    stream = file or sys.stdout
    try:
        print(*args, file=stream, **kwargs)
        return
    except UnicodeEncodeError:
        pass
    enc = getattr(stream, "encoding", None) or "utf-8"
    sep = kwargs.get("sep", " ")
    end = kwargs.get("end", "\n")
    flush = kwargs.get("flush", False)
    text = sep.join(str(a) for a in args) + end
    data = text.encode(enc, errors="replace")
    buf = getattr(stream, "buffer", None)
    if buf is not None:
        buf.write(data)
        if flush:
            buf.flush()
    else:
        stream.write(data.decode(enc, errors="replace"))
        if flush:
            stream.flush()


def summarize_results(results: list[ExtractResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def print_summary(results: list[ExtractResult], elapsed: float, *, stream=None) -> None:
    stream = stream or sys.stdout
    counts = summarize_results(results)
    total = len(results)
    order = ["ok", "skipped", "needs_ocr", "needs_asr", "needs_password", "error"]
    parts = [f"{k}={counts[k]}" for k in order if counts.get(k)]
    extras = [f"{k}={v}" for k, v in sorted(counts.items()) if k not in order]
    parts.extend(extras)
    safe_print("", file=stream)
    safe_print("===== 抽取统计 =====", file=stream)
    safe_print(f"合计: {total}  耗时: {_fmt_duration(elapsed)}", file=stream)
    safe_print("状态: " + (", ".join(parts) if parts else "(无)"), file=stream)
    # short lists for attention statuses
    for label, key in (
        ("失败", "error"),
        ("需OCR", "needs_ocr"),
        ("需ASR", "needs_asr"),
        ("需密码", "needs_password"),
    ):
        names = [Path(r.source).name for r in results if r.status == key]
        if not names:
            continue
        shown = names[:8]
        more = f" ...(+{len(names) - len(shown)})" if len(names) > len(shown) else ""
        safe_print(f"{label}: {', '.join(shown)}{more}", file=stream)
    safe_print("====================", file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="doc-read local extractor")
    parser.add_argument("paths", nargs="+", type=Path, help="files or directories")
    parser.add_argument("--glob", dest="glob", default=None, help="when path is dir, glob filter e.g. *.pdf")
    parser.add_argument("--force", action="store_true", help="re-extract even if raw exists")
    parser.add_argument("--ocr", action="store_true", help="OCR scan PDFs (requires OCR extras)")
    parser.add_argument("--asr", action="store_true", help="transcribe audio (requires faster-whisper)")
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "cuda", "gpu"],
        help="ASR device: auto prefers CUDA when available",
    )
    parser.add_argument("--render-pages", action="store_true", help="also render page PNGs for text PDFs")
    parser.add_argument("--max-render-pages", type=int, default=0, help="limit rendered pages (0=all)")
    parser.add_argument("--dpi", type=int, default=150, help="render DPI for page images")
    parser.add_argument(
        "--password",
        action="append",
        default=[],
        help="extra password to try for encrypted PDF/archives (repeatable; tried after built-in defaults)",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON summary")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress progress lines (summary still prints unless --json)",
    )
    args = parser.parse_args(argv)

    sources = iter_sources(args.paths, args.glob)
    if not sources:
        print("no matching sources", file=sys.stderr)
        return 2

    total = len(sources)
    flags = []
    if args.force:
        flags.append("force")
    if args.ocr:
        flags.append("ocr")
    if args.asr:
        flags.append(f"asr/{args.device}")
    if args.render_pages:
        flags.append("render-pages")
    flag_s = f" flags=[{', '.join(flags)}]" if flags else ""

    # Progress goes to stderr when --json so stdout stays pure JSON.
    progress_stream = sys.stderr if args.json else sys.stdout
    if not args.quiet:
        safe_print(f"===== 开始抽取: {total} 个文件{flag_s} =====", file=progress_stream, flush=True)

    results: list[ExtractResult] = []
    t0 = datetime.now(timezone.utc)
    for i, src in enumerate(sources, start=1):
        name = src.name
        if not args.quiet:
            safe_print(f"[{i}/{total}] 处理中: {name}", file=progress_stream, flush=True)
        one_t0 = datetime.now(timezone.utc)
        result = process_one(
            src,
            force=args.force,
            ocr=args.ocr,
            asr=args.asr,
            render_pages=args.render_pages,
            max_render_pages=args.max_render_pages,
            dpi=args.dpi,
            device=args.device,
            passwords=args.password,
        )
        results.append(result)
        one_elapsed = (datetime.now(timezone.utc) - one_t0).total_seconds()
        if not args.quiet:
            msg = result.message.strip() if result.message else ""
            msg_bit = f" :: {msg}" if msg else ""
            safe_print(
                f"[{i}/{total}] [{result.status}] {name} :: {result.format}{msg_bit}  ({_fmt_duration(one_elapsed)})",
                file=progress_stream,
                flush=True,
            )
            if not args.json:
                if result.raw_path:
                    safe_print(f"  raw: {result.raw_path}", file=progress_stream)
                if result.clean_path:
                    safe_print(f"  clean: {result.clean_path}", file=progress_stream)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()

    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
        if not args.quiet:
            print_summary(results, elapsed, stream=sys.stderr)
    else:
        print_summary(results, elapsed, stream=sys.stdout)

    # non-zero if any hard error
    if any(r.status == "error" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
