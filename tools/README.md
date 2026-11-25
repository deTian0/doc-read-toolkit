# 文档库工具包（tools）

可分享的 Claude Skills 与配套脚本。**不含** `local/` 下的原文文档，也**不含** `.conda` 环境二进制。

本目录是仓库内工具的**真相源**。改 skill / 归档逻辑只改这里，然后在仓库根执行：

```bash
python scripts/sync_skills.py          # 同步到 <repo>/.claude/skills（本机路径替换）
python scripts/build_share_zip.py      # 可选：打 tools.zip
run.bat                                # 仓库根：分类归档 / 抽取一键菜单
```

## 包含内容

```text
tools/
  README.md
  requirements.txt          # 汇总依赖入口
  requement.txt             # 同上（兼容拼写，deprecated）
  .claude/skills/
    doc-read/               # 多格式文档省 token 阅读
    weread-skills/          # 微信读书助手
  paid_doc_archiver/        # 微信下载目录 → local/YYYY-MM[/DD] 归档
  _asr_tools/               # 独立 ASR 小工具（可选）
```

内容库在仓库根的 `local/`（不随本包分发）：

```text
local/
  2026-08/{付费文,未统计}           # 往月：整月
  2026-11/19/{付费文,未统计}        # 当月：YYYY-MM / DD
```

## 1. 路径与环境变量

分享包内使用占位符；本机可通过环境变量避免手改：

| 变量 / 占位符 | 含义 |
|---------------|------|
| `YOUR_DOC_ROOT` / `DOC_READ_ROOT` | 文档库根 |
| `DOC_LOCAL_ROOT` | 内容库根，默认 `YOUR_DOC_ROOT/local` |
| `YOUR_WECHAT_MSG_FILE` / `WECHAT_MSG_FILE` | 微信 `msg\\file` |
| `DOC_READ_PYTHON` | 本地 conda/venv 的 python.exe |
| `WEREAD_API_KEY` | 微信读书 Agent Key |
| `DOC_READ_PASSWORDS` | 额外解压/PDF 密码（逗号分隔） |

也可在文档库根放 `secrets.local.json`（勿提交）：

```json
{ "passwords": ["example"] }
```

抽取解压/加密 PDF 时密码顺序：空 → 脚本内置默认 → `secrets.local.json` → `DOC_READ_PASSWORDS` → `--password`。

## 2. 安装 Python 环境（doc-read）

推荐 **Python 3.12** 本地前缀：

```bash
conda create -y -p "YOUR_DOC_ROOT/.conda/doc-read" python=3.12 -c conda-forge --override-channels
uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" \
  -r "YOUR_DOC_ROOT/tools/.claude/skills/doc-read/scripts/requirements.txt"
# 可选 OCR / ASR：requirements-ocr.txt / requirements-asr.txt
```

## 3. 挂载 Skills

在完整文档库仓库中：把本目录放在 `YOUR_DOC_ROOT/tools/`，运行 `python scripts/sync_skills.py`。

仅使用本包时：复制 `.claude/skills/*` 到项目或用户 skills 目录，并替换 `YOUR_DOC_ROOT`。

## 4. 付费文归档

```bat
cd paid_doc_archiver
python paid_doc_archiver.py "%WECHAT_MSG_FILE%" "%DOC_LOCAL_ROOT%"
```

- 当月 → `local/YYYY-MM/DD/{付费文\|未统计}`
- 往月 → `local/YYYY-MM/{付费文\|未统计}`
- **会移动/可能删除源文件**，先备份或小目录试跑。

## 5. 常用 doc-read 命令

```bat
REM 仓库根一键菜单（推荐）
run.bat

".claude\skills\doc-read\scripts\extract.cmd" local\2026-11\02\付费文 --glob "*.pdf"
".claude\skills\doc-read\scripts\render_rough_report.cmd" --scan-dir "local/2026-11/18/付费文" --also "local/2026-11/18/未统计"
```

抽取时默认打印 `[i/N]` 进度与收尾「抽取统计」；`--json` 时进度走 stderr；`--quiet` 可关掉进度。

## 6. 故障速查

| 现象 | 处理 |
|------|------|
| Missing local env | 设 `DOC_READ_PYTHON` 或替换 `YOUR_DOC_ROOT` |
| 扫描件为空 | `--ocr` + requirements-ocr |
| 音频 needs_asr | `--asr` + requirements-asr（`av>=10,<14`） |
| weread 401 | 检查 `WEREAD_API_KEY` |
| 归档跑错目录 | 检查 `WECHAT_MSG_FILE` / `DOC_LOCAL_ROOT` |
| `run.bat` 路径乱码（如 `鏂囨。`） | `.env.local` 用 UTF-8；勿让 bat 直接 `for /f` 读它 |
| `run.bat` 命令被拆碎 | 保持 **GBK + CRLF**；勿存成纯 LF |
| MuPDF xref 刷屏 | 已在抽取时静音；一般仍可抽到文本 |
| SyntaxWarning `\.conda` | 已修：`sync_skills` 对 `.py` 不再写入反斜杠路径 |
