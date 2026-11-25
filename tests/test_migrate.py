# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import migrate_to_local as m  # noqa: E402


def test_plan_moves_day_and_month(tmp_path: Path):
    (tmp_path / "2026-08").mkdir()
    (tmp_path / "2026-11-19").mkdir()
    (tmp_path / "索引").mkdir()
    (tmp_path / "tools").mkdir()
    plans = {str(src.name): dest for src, dest in m.plan_moves(tmp_path)}
    assert plans["2026-08"] == tmp_path / "local" / "2026-08"
    assert plans["2026-11-19"] == tmp_path / "local" / "2026-11" / "19"
    assert plans["索引"] == tmp_path / "local" / "索引"
