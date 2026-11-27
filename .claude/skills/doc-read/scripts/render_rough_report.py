#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fill the reusable rough-scan HTML template from _extract/*.meta.json.

Usage:
  python render_rough_report.py --scan-dir 2026-11-18/付费文 --also 2026-11-18/未统计
  python render_rough_report.py --scan-dir 2026-11-18/付费文 --out 2026-11-18/索引/粗读-2026-11-18.html
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = SKILL_ROOT / "templates" / "rough_scan_report.html"


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def file_href(path_str: str | None) -> str:
    if not path_str:
        return ""
    p = Path(path_str)
    try:
        if not p.is_absolute():
            # Best-effort: leave as-is if relative and unresolved.
            p = p.resolve()
        return p.as_uri()
    except Exception:
        return ""


def worth_label(value: Any) -> tuple[str, str]:
    if value is True:
        return "建议深读", "deep"
    if value is False:
        return "可跳过", "skip"
    return "待定", "pending"


def status_chip(meta: dict[str, Any]) -> tuple[str, str]:
    status = (meta.get("status") or "").strip() or "unknown"
    msg = (meta.get("message") or "").lower()
    if status in {"needs_password"} or "encrypt" in msg:
        return status or "encrypted", "bad"
    if status in {"error", "needs_ocr", "needs_asr", "skipped_scan"}:
        return status, "bad" if status == "error" else "pending"
    if status in {"ok", "skipped", "partial"}:
        return status, "skip"
    return status, "pending"


def discover_metas(scan_dirs: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()
    for root in scan_dirs:
        root = root.resolve()
        if not root.exists():
            continue
        for meta in sorted(root.rglob("*.meta.json")):
            if "_extract" not in meta.parts:
                continue
            # Skip nested products under archive unpack trees.
            if "_unpacked" in meta.parts:
                continue
            key = str(meta.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(meta)
    return found


def guess_day_dir(scan_dirs: list[Path]) -> Optional[Path]:
    for d in scan_dirs:
        cur = d.resolve()
        # Prefer parent if scanning 付费文/未统计 under a day folder.
        if cur.name in {"付费文", "未统计"} and re.match(r"\d{4}-\d{2}-\d{2}$", cur.parent.name or ""):
            return cur.parent
        if re.match(r"\d{4}-\d{2}-\d{2}$", cur.name or ""):
            return cur
    return scan_dirs[0].resolve().parent if scan_dirs else None


def default_out_path(scan_dirs: list[Path]) -> Path:
    day = guess_day_dir(scan_dirs)
    if day is None:
        day = Path.cwd()
    stamp = day.name if re.match(r"\d{4}-\d{2}-\d{2}$", day.name or "") else datetime.now().strftime("%Y-%m-%d")
    return day / "索引" / f"粗读-{stamp}.html"


def render_stats(items: list[dict[str, Any]]) -> str:
    total = len(items)
    deep = sum(1 for it in items if it.get("worth_deep_read") is True)
    skip = sum(1 for it in items if it.get("worth_deep_read") is False)
    pending = total - deep - skip
    blocked = sum(
        1
        for it in items
        if (it.get("status") or "") in {"error", "needs_password", "needs_ocr", "needs_asr", "skipped_scan"}
    )
    cells = [
        ("全部", total),
        ("建议深读", deep),
        ("可跳过", skip),
        ("待定", pending),
        ("异常/待处理", blocked),
    ]
    parts = []
    for label, n in cells:
        parts.append(
            f'<div class="stat"><b>{n}</b><span>{html.escape(label)}</span></div>'
        )
    return "".join(parts)


def conclusions_html(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return ""
    lis = "".join(f"<li>{html.escape(str(x))}</li>" for x in values if str(x).strip())
    return f"<ul>{lis}</ul>" if lis else ""


def tags_html(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return ""
    return "".join(
        f'<span class="chip">{html.escape(str(t))}</span>' for t in values if str(t).strip()
    )


def render_deep_list(items: list[dict[str, Any]]) -> str:
    deep_items = [it for it in items if it.get("worth_deep_read") is True]
    if not deep_items:
        return '<p class="empty">本批暂无标记为建议深读的篇目。</p>'
    lis: list[str] = []
    for it in deep_items:
        title = html.escape(it.get("title") or Path(str(it.get("source") or "")).stem or "(无标题)")
        one = html.escape(it.get("one_liner") or "")
        summary_href = file_href(it.get("summary_path"))
        source_href = file_href(it.get("source"))
        jumps = []
        if summary_href:
            jumps.append(f'<a href="{html.escape(summary_href, quote=True)}">打开 summary</a>')
        if source_href:
            jumps.append(f'<a href="{html.escape(source_href, quote=True)}">打开源文件</a>')
        lis.append(
            "<li>"
            f"<div><strong>{title}</strong></div>"
            + (f'<div class="one">{one}</div>' if one else "")
            + (f'<div class="jumps">{" · ".join(jumps)}</div>' if jumps else "")
            + "</li>"
        )
    return '<ul class="deep-list">' + "".join(lis) + "</ul>"


def render_cards(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<p class="empty">未找到任何 meta.json。</p>'
    cards: list[str] = []
    for it in items:
        title = html.escape(it.get("title") or Path(str(it.get("source") or "")).stem or "(无标题)")
        author = html.escape(it.get("author") or "")
        date = html.escape(it.get("date") or "")
        fmt = html.escape(it.get("format") or "")
        one = html.escape(it.get("one_liner") or "")
        w_label, w_class = worth_label(it.get("worth_deep_read"))
        s_label, s_class = status_chip(it)
        chips = [
            f'<span class="chip {w_class}">{html.escape(w_label)}</span>',
            f'<span class="chip {s_class}">{html.escape(s_label)}</span>',
        ]
        if fmt:
            chips.append(f'<span class="chip">{fmt}</span>')
        chips_html = "".join(chips) + tags_html(it.get("tags"))
        sub_bits = [x for x in (author, date) if x]
        sub = " · ".join(sub_bits)
        summary_href = file_href(it.get("summary_path"))
        source_href = file_href(it.get("source"))
        jumps = []
        if summary_href:
            jumps.append(f'<a href="{html.escape(summary_href, quote=True)}">summary</a>')
        if source_href:
            jumps.append(f'<a href="{html.escape(source_href, quote=True)}">源文件</a>')
        msg = html.escape(it.get("message") or "")
        cards.append(
            '<article class="card">'
            '<div class="card-head">'
            f"<h3>{title}</h3>"
            f'<div class="chips">{chips_html}</div>'
            "</div>"
            + (f'<div class="sub">{sub}</div>' if sub else "")
            + (f'<p class="one">{one}</p>' if one else "")
            + conclusions_html(it.get("key_conclusions"))
            + (f'<div class="sub">{msg}</div>' if msg and s_class in {"bad", "pending"} else "")
            + (f'<div class="jumps">{" · ".join(jumps)}</div>' if jumps else "")
            + "</article>"
        )
    return "".join(cards)


def fill_template(template: str, mapping: dict[str, str]) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{[A-Z0-9_]+\}\}", out)
    if leftover:
        raise RuntimeError(f"unfilled template placeholders: {sorted(set(leftover))}")
    return out


def sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(it: dict[str, Any]):
        worth = it.get("worth_deep_read")
        worth_rank = 0 if worth is True else 1 if worth is None else 2
        return (worth_rank, str(it.get("date") or ""), str(it.get("title") or ""))

    return sorted(items, key=key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render doc-read rough-scan HTML card report from metas")
    parser.add_argument("--scan-dir", action="append", type=Path, required=True, help="scan root (repeatable)")
    parser.add_argument("--also", action="append", type=Path, default=[], help="extra scan roots")
    parser.add_argument("--out", type=Path, default=None, help="output HTML path")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="HTML template path")
    parser.add_argument("--title", default=None, help="report title override")
    args = parser.parse_args(argv)

    scan_dirs = [p for p in (args.scan_dir + args.also) if p]
    meta_paths = discover_metas(scan_dirs)
    items = []
    for p in meta_paths:
        data = load_json(p)
        if data:
            items.append(data)
    items = sort_items(items)

    out_path = args.out or default_out_path(scan_dirs)
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    day = guess_day_dir(scan_dirs)
    stamp = day.name if day and re.match(r"\d{4}-\d{2}-\d{2}$", day.name or "") else datetime.now().strftime("%Y-%m-%d")
    title = args.title or f"{stamp} 粗读扫描报告"
    scope = "、".join(str(p) for p in scan_dirs)
    generated_at = datetime.now().astimezone().replace(microsecond=0).isoformat()

    template_text = args.template.read_text(encoding="utf-8")
    html_text = fill_template(
        template_text,
        {
            "REPORT_TITLE": html.escape(title),
            "SCAN_SCOPE": html.escape(scope),
            "GENERATED_AT": html.escape(generated_at),
            "STATS_HTML": render_stats(items),
            "DEEP_LIST_HTML": render_deep_list(items),
            "CARDS_HTML": render_cards(items),
        },
    )
    out_path.write_text(html_text, encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"items={len(items)} deep={sum(1 for it in items if it.get('worth_deep_read') is True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
