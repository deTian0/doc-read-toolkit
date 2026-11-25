# 文档库 + 工具包

## 布局

| 路径 | 含义 |
|------|------|
| `local/YYYY-MM[/DD]/` | **内容库**（付费文/未统计/索引）。根目录不再平铺 `2026-*` |
| `tools/` | **工具真相源**（原「打包」项目已吸收）。改 skill / 归档只改这里 |
| `.claude/skills/` | 给 Claude Code 用的同步副本；由脚本从 `tools/` 生成 |
| `scripts/` | `migrate_to_local` / `sync_skills` / `build_share_zip` / `load_dotenv_bat` |
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
# 一键菜单（分类归档 / 抽取；回车用默认路径；读 .env.local）
run.bat

python scripts/sync_skills.py
python scripts/sync_skills.py --check
python scripts/migrate_to_local.py --dry-run

".claude/skills/doc-read/scripts/extract.cmd" local/2026-11/19/付费文 --glob "*.pdf"
".claude/skills/doc-read/scripts/render_rough_report.cmd" --scan-dir "local/2026-11/19/付费文" --also "local/2026-11/19/未统计"

python tools/paid_doc_archiver/paid_doc_archiver.py "%WECHAT_MSG_FILE%" "%DOC_LOCAL_ROOT%"
# 或双击 tools/paid_doc_archiver/run_archive.bat

python -m pytest tests/ -q
```

### `run.bat` 说明

- 菜单：`1` 分类归档，`2` 文档抽取，`0` 退出
- 路径回车 = 默认：归档源 `WECHAT_MSG_FILE`、输出 `DOC_LOCAL_ROOT`；抽取源 `local/YYYY-MM/DD/付费文`（当天）
- 抽取选项可组合：`o`=`--ocr`，`a`=`--asr`，`f`=`--force`
- 抽取产物固定在源旁 `_extract/`；控制台会打 `[i/N]` 进度与收尾统计
- `.env.local` 须 UTF-8；由 `scripts/load_dotenv_bat.py` 加载（避免 GBK bat 直接读乱码）
- `run.bat` 本体为 **GBK + CRLF**（给中文 Windows 双击用）；不要用纯 LF/UTF-8 无 BOM 覆盖

## Skills 何时启用

见 `tools/.claude/skills/doc-read/SKILL.md` 与 `weread-skills/SKILL.md`。粗读批量结束后必须跑模板生成 HTML 卡片，不要手写整页 HTML。
