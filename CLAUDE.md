# 文档库 + 工具包

## 布局

| 路径 | 含义 |
|------|------|
| `local/YYYY-MM[/DD]/` | **内容库**（付费文/未统计/索引）。根目录不再平铺 `2026-*` |
| `tools/` | **工具真相源**（原「打包」项目已吸收）。改 skill / 归档只改这里 |
| `.claude/skills/` | 给 Claude Code 用的同步副本；由脚本从 `tools/` 生成 |
| `scripts/` | `migrate_to_local` / `sync_skills` / `build_share_zip` |
| `docs/工程化提升计划.md` | 工程化约定与验收 |
| `.conda/doc-read/` | 本机 Python 3.12 环境（gitignore） |

当月按日：`local/2026-11/19/付费文`。往月整月：`local/2026-08/付费文`。

## 改工具时

1. 只编辑 `tools/.claude/skills/...` 或 `tools/paid_doc_archiver/...`
2. `python scripts/sync_skills.py`（把 skills 同步到根 `.claude/skills`，并替换本机路径）
3. 可选：`python scripts/build_share_zip.py`（默认保留解压密码；对外加 `--scrub-passwords`）

禁止只改根 `.claude/skills` 却不改 `tools/`（下次 sync 会被覆盖）。

## 环境变量 / 密钥

- `DOC_READ_PYTHON`：本地 python.exe
- `DOC_READ_ROOT`：文档库根（可选）
- `DOC_LOCAL_ROOT`：内容库根，默认 `<repo>/local`
- `WECHAT_MSG_FILE`：微信下载目录
- `WEREAD_API_KEY`：微信读书
- `DOC_READ_PASSWORDS`：额外密码（逗号分隔）
- `secrets.local.json`：`{ "passwords": [...] }`（已 gitignore，见 example）

## 常用命令

```bash
python scripts/sync_skills.py
python scripts/sync_skills.py --check
python scripts/migrate_to_local.py --dry-run

".claude/skills/doc-read/scripts/extract.cmd" local/2026-11/19/付费文 --glob "*.pdf"
".claude/skills/doc-read/scripts/render_rough_report.cmd" --scan-dir "local/2026-11/19/付费文" --also "local/2026-11/19/未统计"

python tools/paid_doc_archiver/paid_doc_archiver.py "%WECHAT_MSG_FILE%" "%DOC_LOCAL_ROOT%"

python -m pytest tests/ -q
```

## Skills 何时启用

见 `tools/.claude/skills/doc-read/SKILL.md` 与 `weread-skills/SKILL.md`。粗读批量结束后必须跑模板生成 HTML 卡片，不要手写整页 HTML。
