# 文档库 Claude Skills 打包

可运行的技能与配套脚本包，**不含**按日归档的原文文档，也**不含** `.conda` 环境二进制。

对方拿到后：替换路径占位符 → 建本地 Python 环境 → 把 skills 挂到 Claude Code →（可选）配置微信读书 API Key / 微信下载目录。

## 包含内容

```text
打包/
  README.md
  requirements.txt          # 汇总依赖入口
  requement.txt             # 同上（兼容拼写）
  .claude/skills/
    doc-read/               # 多格式文档省 token 阅读
      SKILL.md
      scripts/              # extract / OCR / ASR / 粗读卡片
      templates/            # 粗读 HTML 模板
    weread-skills/          # 微信读书助手（API 技能说明）
      SKILL.md + *.md
  paid_doc_archiver/        # 微信下载目录 → 按日/月归档付费文
    paid_doc_archiver.py
    authors.json
    run_archive.bat
    README.md
  _asr_tools/
    transcribe_sitoushe.py  # 独立 ASR 小工具（可选）
```

未打包：`2026-*` 原文、`索引/` 产物、`.conda/` 环境、日志。

## 1. 替换路径占位符

打包版已把本机路径改成占位符：

| 占位符 | 含义 |
|--------|------|
| `YOUR_DOC_ROOT` | 文档库根目录（归档输出、doc-read 环境） |
| `YOUR_WECHAT_MSG_FILE` | 微信 `msg\\file` 下载目录（仅归档工具） |

请在整个 `打包/` 目录内全局替换，例如：

| 平台 | 示例真实路径 |
|------|----------------|
| Windows | `D:\\Docs` 或 `D:/Docs` |
| macOS / Linux | `/home/you/docs` |

需要改到的文件（至少）：

- `.claude/skills/doc-read/SKILL.md`
- `.claude/skills/doc-read/scripts/extract.cmd`
- `.claude/skills/doc-read/scripts/render_rough_report.cmd`
- `.claude/skills/doc-read/scripts/extract_docs.py`
- `.claude/skills/doc-read/scripts/bench_device.py`
- `.claude/skills/doc-read/scripts/requirements.txt`（注释）
- `paid_doc_archiver/paid_doc_archiver.py`
- `paid_doc_archiver/run_archive.bat`
- `paid_doc_archiver/README.md`

也可用环境变量绕过 `.cmd` 硬编码：

```bat
set DOC_READ_PYTHON=D:\Docs\.conda\doc-read\python.exe
```

## 2. 安装 Python 环境（doc-read）

推荐 **Python 3.12** 本地前缀（勿用过新的全局 Python，OCR/ASR 轮子常缺）。

```bash
# 把 YOUR_DOC_ROOT 换成真实路径
conda create -y -p "YOUR_DOC_ROOT/.conda/doc-read" python=3.12 -c conda-forge --override-channels

uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" \
  -r "YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/requirements.txt"

# 可选：扫描件 OCR
uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" \
  -r "YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/requirements-ocr.txt"

# 可选：音频转写（faster-whisper；注意 av 版本钉死在 requirements-asr.txt）
uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" \
  -r "YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/requirements-asr.txt"
```

没有 conda / uv 时，也可用 venv + pip：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
set DOC_READ_PYTHON=%CD%\.venv\Scripts\python.exe
```

系统依赖（按需）：

- 解压 `.zip`：Python 标准库即可
- `.rar` / `.7z`：安装 [7-Zip](https://www.7-zip.org/)（`.rar` 也可退回 WinRAR 的 `UnRAR.exe`）
- GPU ASR/OCR：本机 CUDA 与对应驱动（可选）

## 3. 安装 Skills 到 Claude Code

把本包里的 `.claude/skills/*` 放到对方的**文档库根**下同名路径，或复制到用户级技能目录：

```text
# 项目级（推荐，随文档库走）
YOUR_DOC_ROOT/.claude/skills/doc-read/
YOUR_DOC_ROOT/.claude/skills/weread-skills/

# 或用户级
~/.claude/skills/doc-read/
~/.claude/skills/weread-skills/
```

在 Claude Code 打开 `YOUR_DOC_ROOT` 后，对话里应能看到 / 调用 `doc-read`、`weread-skills`。

## 4. 微信读书（weread-skills）

该技能通过官方 Agent Gateway 调用接口，**需要 API Key**：

```bash
# Windows PowerShell
$env:WEREAD_API_KEY = "wrk-xxxxxxxx"

# bash
export WEREAD_API_KEY=wrk-xxxxxxxx
```

Key 格式 `wrk-...`，绑定用户身份。未设置时技能会提示配置。详见 `.claude/skills/weread-skills/SKILL.md`。

## 5. 付费文归档（paid_doc_archiver）

把微信下载目录（`msg\\file` 下的 `YYYY-MM` 月文件夹）按修改时间与作者关键字，**移动**整理到文档库的 `付费文/` / `未统计/`。仅需 Python 3.9+ 标准库。

```bat
cd paid_doc_archiver
REM 先编辑 run_archive.bat 顶部的 SOURCE / OUTPUT，或：
python paid_doc_archiver.py "YOUR_WECHAT_MSG_FILE" "YOUR_DOC_ROOT"
```

- 关键字列表：`paid_doc_archiver/authors.json`（可自行增删）
- 当月 → `YOUR_DOC_ROOT/YYYY-MM-DD/{付费文|未统计}`
- 往月 → `YOUR_DOC_ROOT/YYYY-MM/{付费文|未统计}`
- **会移动/可能删除源文件**，先备份或小目录试跑。详见 `paid_doc_archiver/README.md`。

## 6. 常用命令（doc-read）

```bat
REM 单文件抽取
".claude\skills\doc-read\scripts\extract.cmd" path\to\file.pdf

REM 目录批量
".claude\skills\doc-read\scripts\extract.cmd" 2026-11-02\付费文 --glob "*.pdf"

REM 扫描件 OCR / 音频 ASR
extract.cmd scan.pdf --ocr --force
extract.cmd talk.mp3 --asr

REM 粗读 HTML 卡片
".claude\skills\doc-read\scripts\render_rough_report.cmd" --scan-dir "2026-11-18\付费文" --also "2026-11-18\未统计"
```

产物约定（写在源文件旁）：

```text
_extract/<stem>.raw.txt
_extract/<stem>.clean.md
_extract/<stem>.summary.md
_extract/<stem>.meta.json
索引/粗读-YYYY-MM-DD.html
```

## 7. 加密压缩包 / PDF 密码

按发送方要求，**打包版保留了库内常用密码**（与 `doc-read` 的 `DEFAULT_PASSWORDS` / `SKILL.md` 一致）。
仅用于解开同一批加密附件；若你要再分发，请自行评估是否继续保留。

也可用命令行追加：`extract.cmd secret.pdf --password extra`。

## 8. 建议的文档库布局

```text
YOUR_DOC_ROOT/
  .claude/skills/          # 本包技能
  .conda/doc-read/         # 本地 Python（自建）
  paid_doc_archiver/       # 可选：归档工具也可放这里
  YYYY-MM-DD/
    付费文/
    未统计/
    索引/
```

## 9. 故障速查

| 现象 | 处理 |
|------|------|
| `.cmd` 报 Missing local env | 替换 `YOUR_DOC_ROOT`，或设 `DOC_READ_PYTHON` |
| 扫描件抽字为空 | 加 `--ocr` 并安装 `requirements-ocr.txt` |
| 音频提示 needs_asr | 加 `--asr` 并安装 `requirements-asr.txt` |
| `av` / faster-whisper 报错 | 使用打包内 `requirements-asr.txt`（钉死 `av>=10,<14`） |
| rar/7z 失败 | 安装 7-Zip；确认 `7z` 在 PATH |
| weread 401 | 检查 `WEREAD_API_KEY` |
| 归档跑错目录 | 检查 `YOUR_WECHAT_MSG_FILE` / `YOUR_DOC_ROOT`；先小目录试跑 |

## License / 来源

- `doc-read`：文档库本地预处理与 Claude Code skill
- `weread-skills`：微信读书 Agent API 技能说明（调用需自备 Key）
- `paid_doc_archiver`：付费文按日/月归档（stdlib-only）
