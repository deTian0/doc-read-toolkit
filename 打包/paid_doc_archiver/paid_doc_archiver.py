# -*- coding: utf-8 -*-
"""
付费文按日/按月归档（独立可转发版）

依赖：Python 3.9+ 标准库（见 requirements.txt）

用法：
  python paid_doc_archiver.py
  python paid_doc_archiver.py "D:\\path\\to\\source" "D:\\path\\to\\output"
  或双击 run_archive.bat

规则：
  - 源根下 YYYY-MM 月目录：当月按 mtime 归到 输出/YYYY-MM-DD/{付费文|未统计}
  - 往月有文件：归到 输出/YYYY-MM/{付费文|未统计}
  - 文件名命中 authors.json 关键字 → 付费文，否则 → 未统计
  - 操作为移动；同名同内容删源；同名不同内容改名 name (1).ext
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

CATEGORY_PAID = "付费文"
CATEGORY_UNTRACKED = "未统计"

_DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_READ_CHUNK = 1024 * 1024
_OPEN_RETRIES = 4
_RETRY_DELAY_SEC = 0.12

HERE = Path(__file__).resolve().parent

# 可按需修改；也可用命令行参数覆盖
# Replace placeholders before first run, or pass CLI args / edit run_archive.bat.
DEFAULT_SOURCE = Path(r"YOUR_WECHAT_MSG_FILE")
DEFAULT_OUTPUT = Path(r"YOUR_DOC_ROOT")


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def setup_logger(log_dir: Path, log_name: str = "paid_doc_archiver") -> logging.Logger:
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    log_file = log_dir / f"{log_name}_{ts}.log"

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info("日志文件: %s", log_file)
    return logger


# ---------------------------------------------------------------------------
# 作者关键字
# ---------------------------------------------------------------------------

def load_author_tokens(path: Optional[Path] = None) -> List[str]:
    authors_path = path or (HERE / "authors.json")
    if not authors_path.exists():
        raise FileNotFoundError(
            f"找不到作者关键字文件: {authors_path}\n请确保与本脚本同目录有 authors.json"
        )
    data = json.loads(authors_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("authors.json 须为字符串数组")
    tokens = [str(x).strip() for x in data if str(x).strip()]
    # 长名优先，降低短词误匹配
    return sorted(set(tokens), key=len, reverse=True)


def classify_category(file_name: str, author_tokens: Iterable[str]) -> str:
    for token in author_tokens:
        if token and token in file_name:
            return CATEGORY_PAID
    return CATEGORY_UNTRACKED


# ---------------------------------------------------------------------------
# 移动 / 冲突
# ---------------------------------------------------------------------------

def calculate_file_md5(file_path: Path) -> str:
    last_err: Optional[OSError] = None
    for attempt in range(_OPEN_RETRIES):
        try:
            with open(file_path, "rb", buffering=_READ_CHUNK) as f:
                if hasattr(hashlib, "file_digest"):
                    return hashlib.file_digest(f, "md5").hexdigest()
                h = hashlib.md5()
                for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
                    h.update(chunk)
                return h.hexdigest()
        except (OSError, PermissionError) as e:
            last_err = e
            if attempt + 1 < _OPEN_RETRIES:
                time.sleep(_RETRY_DELAY_SEC)
                continue
            return ""
    return "" if last_err else ""


def files_identical(path_a: Path, path_b: Path) -> bool:
    try:
        if path_a.stat().st_size != path_b.stat().st_size:
            return False
    except OSError:
        return False
    a, b = calculate_file_md5(path_a), calculate_file_md5(path_b)
    return bool(a and b and a == b)


def unique_dest(folder: Path, document_name: str, claimed: Set[str], logger: logging.Logger) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / document_name
    if str(candidate) not in claimed and not candidate.exists():
        claimed.add(str(candidate))
        return candidate
    stem, suffix = Path(document_name).stem, Path(document_name).suffix
    index = 1
    while True:
        alt = f"{stem} ({index}){suffix}"
        candidate = folder / alt
        if str(candidate) not in claimed and not candidate.exists():
            claimed.add(str(candidate))
            logger.info("  同名冲突，改用: %s", alt)
            return candidate
        index += 1


def _move_file(src: Path, dest: Path, logger: logging.Logger) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        logger.info("  移动: %s -> %s", src, dest)
        return True
    except OSError:
        try:
            shutil.copy2(str(src), str(dest))
            src.unlink()
            logger.info("  跨盘复制后删除源: %s -> %s", src, dest)
            return True
        except OSError as e:
            logger.warning("  移动失败 %s -> %s: %s", src, dest, e)
            return False


def safe_move(src: Path, dest_folder: Path, claimed: Set[str], logger: logging.Logger) -> str:
    if not src.exists() or not src.is_file():
        logger.warning("  源不存在或非文件，跳过: %s", src)
        return "failed"

    dest_folder.mkdir(parents=True, exist_ok=True)
    original = dest_folder / src.name
    if original.exists():
        try:
            same_file = original.resolve() == src.resolve()
        except OSError:
            same_file = False
        if same_file:
            logger.info("  源已在目标位置，跳过: %s", src)
            return "moved"
        if files_identical(src, original):
            try:
                src.unlink()
                logger.info("  目标已存在且内容相同，删除源: %s", src)
                return "identical_removed"
            except OSError as e:
                logger.warning("  删除相同源失败 %s: %s", src, e)
                return "failed"

    dest = unique_dest(dest_folder, src.name, claimed, logger)
    if _move_file(src, dest, logger):
        return "moved"
    claimed.discard(str(dest))
    return "failed"


# ---------------------------------------------------------------------------
# 归档逻辑
# ---------------------------------------------------------------------------

def list_source_files(source: Path, recursive: bool) -> List[Path]:
    if not source.exists():
        return []
    if recursive:
        return sorted(p for p in source.rglob("*") if p.is_file())
    return sorted(p for p in source.iterdir() if p.is_file())


def day_key_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def archive_daily(
    source: Path,
    daily_root: Path,
    author_tokens: List[str],
    recursive: bool,
    logger: logging.Logger,
) -> Tuple[int, int, int, int]:
    files = list_source_files(source, recursive)
    daily_resolved = daily_root.resolve()
    filtered: List[Path] = []
    for f in files:
        try:
            resolved = f.resolve()
            if daily_resolved in resolved.parents or resolved.parent == daily_resolved:
                rel_parts = resolved.relative_to(daily_resolved).parts
                if rel_parts and _DAY_DIR_RE.match(rel_parts[0]):
                    continue
        except (OSError, ValueError):
            pass
        filtered.append(f)

    logger.info("按日归档: 源=%s → %s，待处理 %d", source, daily_root, len(filtered))
    claimed: Set[str] = set()
    moved = identical = failed = 0
    for path in filtered:
        try:
            day = day_key_from_mtime(path)
        except OSError as e:
            logger.warning("无法读取 mtime，跳过 %s: %s", path, e)
            failed += 1
            continue
        category = classify_category(path.name, author_tokens)
        result = safe_move(path, daily_root / day / category, claimed, logger)
        if result == "moved":
            moved += 1
        elif result == "identical_removed":
            identical += 1
        else:
            failed += 1
    logger.info("按日归档完成: 移动 %d，相同删源 %d，失败 %d", moved, identical, failed)
    return moved, identical, failed, len(filtered)


def archive_into_month(
    source: Path,
    monthly_root: Path,
    month: str,
    author_tokens: List[str],
    recursive: bool,
    logger: logging.Logger,
) -> Tuple[int, int, int, int]:
    if not _MONTH_RE.match(month):
        raise ValueError("月份格式须为 YYYY-MM，收到: %s" % month)
    files = list_source_files(source, recursive)
    logger.info("按月分类: 源=%s → %s，待处理 %d", source, monthly_root / month, len(files))
    claimed: Set[str] = set()
    moved = identical = failed = 0
    for path in files:
        category = classify_category(path.name, author_tokens)
        result = safe_move(path, monthly_root / month / category, claimed, logger)
        if result == "moved":
            moved += 1
        elif result == "identical_removed":
            identical += 1
        else:
            failed += 1
    logger.info("按月分类完成: 移动 %d，相同删源 %d，失败 %d", moved, identical, failed)
    return moved, identical, failed, len(files)


def _iter_day_dirs_for_month(daily_root: Path, month: str) -> List[Path]:
    if not daily_root.exists():
        return []
    return [
        child
        for child in sorted(daily_root.iterdir())
        if child.is_dir() and _DAY_DIR_RE.match(child.name) and child.name.startswith(month + "-")
    ]


def _remove_empty_dir_tree(path: Path, logger: logging.Logger) -> bool:
    if not path.exists():
        return True
    try:
        for child in sorted(path.iterdir(), reverse=True):
            if child.is_dir():
                _remove_empty_dir_tree(child, logger)
        if any(path.iterdir()):
            logger.warning("  目录非空，保留: %s", path)
            return False
        path.rmdir()
        logger.info("  已删除空目录: %s", path)
        return True
    except OSError as e:
        logger.warning("  删除目录失败 %s: %s", path, e)
        return False


def rollup_monthly(
    daily_root: Path,
    monthly_root: Path,
    month: str,
    logger: logging.Logger,
) -> Tuple[int, int, int, int]:
    """将日目录扁平移入月目录（可选高级功能）。"""
    if not _MONTH_RE.match(month):
        raise ValueError("月份格式须为 YYYY-MM，收到: %s" % month)
    day_dirs = _iter_day_dirs_for_month(daily_root, month)
    logger.info("按月归纳: %s，日目录 %d → %s", month, len(day_dirs), monthly_root / month)
    claimed: Set[str] = set()
    moved = identical = failed = 0
    for day_dir in day_dirs:
        for category in (CATEGORY_PAID, CATEGORY_UNTRACKED):
            cat_dir = day_dir / category
            if not cat_dir.is_dir():
                continue
            dest_folder = monthly_root / month / category
            for path in sorted(p for p in cat_dir.rglob("*") if p.is_file()):
                result = safe_move(path, dest_folder, claimed, logger)
                if result == "moved":
                    moved += 1
                elif result == "identical_removed":
                    identical += 1
                else:
                    failed += 1
        for path in sorted(p for p in day_dir.iterdir() if p.is_file()):
            result = safe_move(path, monthly_root / month / CATEGORY_UNTRACKED, claimed, logger)
            if result == "moved":
                moved += 1
            elif result == "identical_removed":
                identical += 1
            else:
                failed += 1
        _remove_empty_dir_tree(day_dir, logger)
    logger.info("按月归纳完成: 移动 %d，相同删源 %d，失败 %d", moved, identical, failed)
    return moved, identical, failed, len(day_dirs)


# ---------------------------------------------------------------------------
# 一键批处理
# ---------------------------------------------------------------------------

def _count_files(folder: Path) -> int:
    if not folder.exists():
        return 0
    return sum(1 for p in folder.iterdir() if p.is_file())


def _month_dirs(source_root: Path) -> List[Path]:
    if not source_root.exists():
        return []
    return sorted(p for p in source_root.iterdir() if p.is_dir() and _MONTH_RE.match(p.name))


def run_batch(
    source_root: Optional[Path] = None,
    output_root: Optional[Path] = None,
    current_month: Optional[str] = None,
    authors_path: Optional[Path] = None,
) -> Tuple[int, int, int]:
    source_root = Path(source_root or DEFAULT_SOURCE)
    output_root = Path(output_root or DEFAULT_OUTPUT)
    current_month = current_month or datetime.now().strftime("%Y-%m")
    author_tokens = load_author_tokens(authors_path)

    output_root.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(output_root)
    logger.info("=" * 60)
    logger.info("一键归档开始")
    logger.info("源: %s", source_root)
    logger.info("出: %s", output_root)
    logger.info("当月按日: %s；作者关键字: %d", current_month, len(author_tokens))

    if not source_root.exists():
        logger.error("源根目录不存在: %s", source_root)
        return 0, 0, 0

    total_moved = total_identical = total_failed = 0
    processed = 0

    for month_dir in _month_dirs(source_root):
        n = _count_files(month_dir)
        if n == 0:
            logger.info("跳过空目录: %s", month_dir.name)
            continue
        processed += 1
        month = month_dir.name
        if month == current_month:
            logger.info("--- %s：按日（%d）---", month, n)
            moved, identical, failed, _ = archive_daily(
                month_dir, output_root, author_tokens, False, logger
            )
        else:
            logger.info("--- %s：按月（%d）---", month, n)
            moved, identical, failed, _ = archive_into_month(
                month_dir, output_root, month, author_tokens, False, logger
            )
        total_moved += moved
        total_identical += identical
        total_failed += failed

    if any(p.is_file() for p in source_root.iterdir()):
        logger.info("--- 源根散落文件：按日 ---")
        moved, identical, failed, _ = archive_daily(
            source_root, output_root, author_tokens, False, logger
        )
        total_moved += moved
        total_identical += identical
        total_failed += failed
        processed += 1

    logger.info("=" * 60)
    logger.info(
        "完成: 批次=%d 移动=%d 相同删源=%d 失败=%d",
        processed,
        total_moved,
        total_identical,
        total_failed,
    )
    logger.info("=" * 60)
    return total_moved, total_identical, total_failed


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = Path(argv[0]) if len(argv) >= 1 and argv[0].strip() else None
    output = Path(argv[1]) if len(argv) >= 2 and argv[1].strip() else None
    moved, identical, failed = run_batch(source, output)
    print(f"完成: 移动 {moved}，相同跳过 {identical}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
