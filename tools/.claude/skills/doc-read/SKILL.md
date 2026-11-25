---
name: doc-read
description: 多格式文档（PDF/docx/扫描件/音频）省 token 阅读流程。用户说读文档、摘要、精读、粗读、建索引、抽文本、OCR、转写，或给出文档路径要你阅读时使用；默认本地抽取→分层读→摘要落盘；批量/按日粗读结束后必须自动用固定模板生成 HTML 卡片报告，禁止手写整页 HTML、禁止把可抽字原文整份反复塞进上下文。
---

# 文档阅读省 Token（doc-read）

本 skill 只在当前文档库（`YOUR_DOC_ROOT`）生效。目标：**本地预处理不计 token，模型只吃已变小的文本；一次算、多次复用。**

## 何时启用

- 用户给出文档路径并要求阅读 / 摘要 / 对比 / 精读 / 粗读
- 用户说「抽文本」「OCR」「转写」「建索引」「出卡片」「按 doc-read」
- 批量处理某日 `付费文/`、`未统计/` 下的 PDF / docx / 音频

不要在无关编码任务上主动套用本 skill。

## 硬性规则（省 token）

1. **有可抽字文本就只读文本产物**，不要把整份可搜索 PDF / docx 当 `document` 或截图反复塞进上下文。
2. **读取优先级（强制）**：`summary.md` + `meta.json` →（仅当需要原文）`clean.md` 局部 →（排错/重抽）`raw.txt`。**有 summary 时默认禁止通读 clean/raw。**
3. **先结构、后精读**：未获用户确认前，不要通读全文；先给 ≤200 字结构摘要（标题/章节/关键结论/是否值得深读）。
4. **按需局部读**：优先按页码、章节、关键词定位；用 `Read` 局部或读 `_extract` 产物，禁止整篇粘贴进回复。
5. **摘要必须落盘**：深读或结构摘要完成后写入约定路径；后续追问优先读摘要 / meta，不重读原文。
6. **新开会话做深读**：长对话已堆积多篇文档历史时，建议用户新开 chat，只挂当前篇产物。
7. **扫描件 / 音频先本地落盘再读**：OCR、Whisper 各做一次；禁止每次用 Vision「看」同一扫描件，禁止反复丢音频给模型。
8. **粗读结束自动出 HTML 卡片（强制）**：凡批量/按日粗读，或用户说「建索引 / 今天这些 / 粗读这批」，在各篇 `summary.md`+`meta.json` 与 markdown 索引写完后，**立刻**跑 `render_rough_report.cmd` 填模板生成 `索引/粗读-YYYY-MM-DD.html`。不要问「要不要出卡片」；禁止手写/即兴生成整页 HTML；聊天只回统计 + 报告路径 + 建议深读标题。

## 一句话口令（用户可直接发）

> 先抽文本/读现有 txt → 给结构摘要并落盘 → 自动生成粗读 HTML 卡片 → 等我指定段落再精读；不要把全文贴进回复。

---

## 产物目录约定

相对**源文件所在目录**（例如 `2026-11-02/付费文/某篇.pdf`）：

```text
付费文/
  某篇.pdf
  _extract/
    某篇.raw.txt          # 本地抽取原文（保留分页标记）
    某篇.clean.md         # 去页眉页脚/导航噪音后的可读正文
    某篇.summary.md       # 结构/精读摘要（给人看）
    某篇.meta.json        # 机器可读元数据
    imgs/                 # 仅扫描件或必须看图时：页图，命名 某篇_pN.png
索引/
  2026-11.md              # 按月/按日一览（可选，放在文档库根或该月目录）
  粗读-2026-11-18.html    # 粗读批量卡片报告（模板填数据生成）
```

### 命名规则

- stem = 源文件主名（不含扩展名），产物一律 `stem.<kind>.<ext>`。
- 旧实验产物（如 `_pdf_txt/1_ok.txt`、`1_pypdf.txt`）**可读作输入**，但新写入必须用上述命名，不要继续扩散数字编号。
- 若 `_extract/stem.raw.txt` 已存在且非空 → **跳过抽取**，直接进入清洗/摘要，除非用户要求重抽。

### `meta.json` 最小字段

```json
{
  "source": "相对或绝对源路径",
  "title": "",
  "author": "",
  "date": "YYYY-MM-DD 或原文日期串",
  "format": "pdf-text|pdf-scan|docx|audio",
  "tags": [],
  "one_liner": "一句话要点",
  "worth_deep_read": null,
  "key_conclusions": [],
  "extracted_at": "ISO-8601",
  "summary_path": "_extract/某篇.summary.md"
}
```

### `summary.md` 推荐结构

```markdown
# <标题>

- 来源：
- 作者/账号：
- 日期：
- 一句话：
- 是否建议深读：是/否 — 理由

## 结构
- ...

## 关键结论
- ...

## 可引用原文（短摘）
> ...

## 待澄清 / 未读部分
- ...
```

### 日/月索引（`索引/YYYY-MM.md`）

表格列：`日期 | 标题 | 作者 | 一句话 | 是否深读 | 源路径 | summary 路径`。

### 粗读 HTML 卡片报告（自动；模板填数据）

**触发（自动，无需用户再吩咐）**：

- 批量/按日粗读结束（`付费文` / `未统计` 任一或同时）
- 用户说「建索引」「今天这些」「粗读这批」「出卡片」
- 批量改了多篇 `worth_deep_read` / `one_liner` 后（刷新卡片）

流水线固定为：各篇 `summary.md` + `meta.json` 落盘 → 更新 `索引/YYYY-MM-DD.md`（及可选月索引）→ **马上**跑渲染脚本 → 把 HTML 路径回给用户。

```bash
"YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/render_rough_report.cmd" ^
  --scan-dir "local/2026-11/18/付费文" --also "local/2026-11/18/未统计"
# 默认写出：local/2026-11/18/索引/粗读-2026-11-18.html
```

约定：

- **自动化**：代理自己调用脚本；默认不要问「要不要生成卡片」。
- **模板固定**：只许填 `templates/rough_scan_report.html`；禁止每次在对话里新写整页 HTML/CSS。
- **数据来源**：各篇 `_extract/*.meta.json`（`one_liner` / `worth_deep_read` / `key_conclusions` / `summary_path` / `source`）。缺字段先补 meta，再渲染。
- **合并粒度**：同一自然日的 `付费文`+`未统计` 合并进一份 `粗读-YYYY-MM-DD.html`。
- **报告内容**：全部粗读卡片 + 顶部「建议深读」；跳转用 `file://` 打开 `summary.md` 与源文件。
- **聊天只回**：篇数统计 + HTML 路径 + 建议深读标题列表；不要贴卡片 HTML 源码。

---

## 本地抽取规则

在调用模型阅读前，按格式走本地预处理。优先复用已有产物。

### 1. 文字 PDF / docx（大头）

- **工具**：PDF 用 `pypdf` 或 `pdfplumber`；Word 用 `python-docx`（`.doc` 先转 docx 或用可用的本地转换）。
- **输出**：`_extract/stem.raw.txt`。PDF 建议保留 `=====PAGE N=====` 分页标记，便于按页精读。
- **清洗**：去站点导航、页眉页脚、重复「相关报道」列表等 → `stem.clean.md`。
  - PDF/docx：导航噪音过滤。
  - 音频：去片头片尾套话、合并 ASR 碎行、保守同音纠错词表；**不重跑模型**。
  - 已有 `raw.txt` 时再次执行脚本（不加 `--force`）会 **刷新 clean**。
- **阅读**：默认读 `summary`；精读才读 `clean.md`；`raw.txt` 仅排错。禁止再塞 PDF/音频二进制。

### 2. 图片型 PDF（扫描件）

- **判定**：抽文本后几乎无字 / 乱码 / 仅空白 → 视为扫描件，`meta.format = pdf-scan`。
- 脚本会先把页图落到 `imgs/stem_pN.png`；加 `--ocr` 时用本地 OCR（默认 RapidOCR）回填 `raw.txt`。
- OCR 正文写入 `stem.raw.txt`，之后当文字 PDF 处理。
- **禁止**：每次用 Vision 重新「看」同一扫描件。

### 3. 音频（mp3 / m4a / wav）

- **本地 Whisper（或同等 ASR）一次** → `_extract/stem.transcript.txt`（脚本同时写入阅读用的 `stem.raw.txt`）。
- 需要 `--asr`，并已安装 `requirements-asr.txt`（faster-whisper）。
- 之后只跑文本管线；**禁止**反复把音频丢给模型。

### 4. 超长单篇

- 按标题或页切块（约 800–1500 字），可选块级一行摘要。
- 问答时先定位相关块，只把 top-k 块（通常 3–8）给模型。

### 5. 有密码的压缩包 / 加密 PDF

遇到加密文件时，**先按下列顺序自动尝试**（已写入脚本常量，勿改口令、勿在聊天里反复复述）：

1. `36903690`
2. `931226`

适用范围：

- **压缩包**：`.zip` / `.rar` / `.7z`（以及常见的「加密附件」）。先无密码试一次，失败再按上表顺序试。
- **加密 PDF**：`extract_docs.py` 打开时同样按上表尝试；成功后再走文字层 / 扫描件流程。

约定：

- 压缩包解压到源旁 `_extract/_unpacked/<stem>/`，再对解出的 pdf/docx/音频跑现有抽取；不要把整包二进制塞进上下文。
- 两个库内密码都失败 → 如实报 `needs_password`，**停下来问用户**，不要猜更多密码、不要改去 Vision 硬看。
- 用户另行给出新密码时，该次优先用用户密码；若用户说「以后也用」，再追加进本 skill 与脚本常量。

### 抽取执行约定

- **优先跑一键脚本**（见下方「本地环境与一键脚本」）；不要手写临时抽取逻辑，除非脚本不覆盖该格式。
- 下载/解压的不可信文件：放独立空目录处理；你写的脚本放另一目录；对不可信输入用 `python -I`。
- 抽取失败时如实报告，不要改去 Vision「硬看」糊弄，除非用户明确要求看图。
- 加密压缩包 / PDF：先用 skill 内置的两个压缩密码自动尝试（见上节）。

---

## 本地环境与一键脚本

隔离环境（不污染本机全局 Python）：

```text
YOUR_DOC_ROOT/.conda/doc-read          # conda 本地前缀，Python 3.12
YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/
  extract_docs.py                # 主脚本
  extract.cmd                    # Windows 包装：自动用本地解释器
  render_rough_report.py         # 粗读 HTML 卡片：模板填数据
  render_rough_report.cmd
  requirements.txt               # 核心：pypdf / pymupdf / python-docx
  requirements-ocr.txt           # 可选：rapidocr-onnxruntime
  requirements-asr.txt           # 可选：faster-whisper
templates/
  rough_scan_report.html         # 粗读报告固定模板（勿每次手写新 HTML）
```

### 创建 / 修复环境

```bash
# 若频道配置有坏的 custom_channels，必须加 --override-channels
conda create -y -p "YOUR_DOC_ROOT/.conda/doc-read" python=3.12 -c conda-forge --override-channels
uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" -r "YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/requirements.txt"
# 扫描件 OCR（可选）
uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" -r "YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/requirements-ocr.txt"
# 音频转写（可选）
uv pip install --python "YOUR_DOC_ROOT/.conda/doc-read/python.exe" -r "YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/requirements-asr.txt"
```

### 常用命令

```bash
# 单文件
"YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/extract.cmd" "path/to/file.pdf"

# 目录批量（只 pdf）
"YOUR_DOC_ROOT/.claude/skills/doc-read/scripts/extract.cmd" "local/2026-11/02/付费文" --glob "*.pdf"

# 扫描件 OCR / 强制重抽 / 音频
extract.cmd scan.pdf --ocr --force
extract.cmd talk.mp3 --asr

# 加密压缩包 / 加密 PDF（自动试内置两密码；可追加）
extract.cmd packed.zip
extract.cmd secret.pdf --password extra

# 粗读 HTML 卡片（模板填 meta；默认同日索引目录）
render_rough_report.cmd --scan-dir "2026-11-18/付费文" --also "2026-11-18/未统计"

# 机器可读汇总
extract.cmd file.pdf --json
```

行为要点：

- 已有非空 `raw.txt` 默认跳过重抽，但会 **刷新 clean**（`--force` 才重跑 ASR/OCR/抽字）。
- ASR 默认 `--device auto`（有 CUDA 用 GPU）。
- 扫描件无 `--ocr`：渲染页图并标记 `needs_ocr`。
- 音频无 `--asr`：标记 `needs_asr`，不瞎调用云端。
- `.doc` 不直接支持，需先转 `.docx`。
- 加密 PDF / zip：先空密码，再试 skill 内置两压缩密码；可用 `--password` 追加。都失败 → `needs_password`。
- `.rar`：优先 7-Zip；若无则用本机 WinRAR `UnRAR.exe`（PATH 与常见 Program Files 路径）。
- `.7z` 仍需要本机 `7z`（UnRAR 不解 7z）。

代理在 doc-read 流程里需要抽取时：**调用上述脚本**，不要用本机 `python`/全局 site-packages。

---

## 对话工作法（和用户协作时）

### 默认流程

1. **定位产物（按优先级）**：
   - 已有 `summary.md` → **只读 summary + meta**，直接回答 / 更新索引；不要打开 clean/raw。
   - 无 summary、有 `clean.md` → 基于 clean 写结构摘要并落盘，然后停。
   - 无 clean、有 `raw.txt` → 先跑/刷新清洗，再摘要。
   - 都无 → 先跑本地抽取脚本。
2. **结构摘要**（≤200 字 + 是否值得深读）→ 写入 `summary.md` 初稿，并更新 `meta.json`。
3. **批量/按日粗读收尾（自动，强制）**：
   1) 更新 `索引/YYYY-MM-DD.md`（及可选月索引）；
   2) **立即**跑 `render_rough_report.cmd`（付费文 + 未统计一并 `--also`）；
   3) 聊天交付：统计 + `粗读-YYYY-MM-DD.html` 路径 + 建议深读标题；
   4) 然后停，等用户点名深读。单篇「读一下」不必出总卡片；一旦是「今天这些 / 建索引 / 粗读这批」或实际扫了多篇，就必须出。
4. **等用户指定**：页码 / 章节 / 关键词 / 「深读全文」后再读 `clean.md` 局部或全文。
5. **精读结果写回** `summary.md`（补全关键结论与短摘），更新 `worth_deep_read` 与 `key_conclusions`；若批量深读标记有变，**再跑一次**渲染脚本刷新卡片。
6. **多篇对比**默认只塞各篇 summary。

### 用户一句话时的默认理解

| 用户说 | 你做 |
|--------|------|
| 「读一下这篇」 | 抽取（如需）→ 结构摘要落盘 → 停，问是否精读；有 summary 则只读 summary（单篇不出总卡片） |
| 「精读 / 深读」 | 读 `clean.md`（不要 raw），写完整 summary，仍避免把全文贴进聊天 |
| 「只看关于 X」 | 在 clean 里检索相关段/页，只读命中部分 |
| 「今天这些 / 建索引 / 粗读这批」 | 批量结构摘要 + markdown 索引 + **自动** `render_rough_report` 出 HTML 卡片（不问要不要） |
| 「出卡片 / 刷新卡片」 | 不重读正文；直接按现有 meta 跑 `render_rough_report` |
| 「重抽」 | 覆盖 `raw.txt`，刷新 clean；旧 summary 是否作废先问用户 |
| 「刷新清洗」 | 不重跑 ASR/OCR，仅按 raw 重建 clean |

### 回复卫生

- 聊天里给结论、结构、短摘与路径链接；**不要**把全文或大段 raw 贴进回复。
- 引用原文用短摘（几句）+ 页码/标题定位。
- 多篇对比时，以各篇 `summary.md` 为输入，不够再回读原文局部。

---

## 快速检查清单

- [ ] 是否已有 `summary.md`？有则先只读 summary/meta
- [ ] 是否已有 `_extract/stem.raw.txt` 或 `clean.md`？有则跳过重抽（可刷新 clean）
- [ ] 扫描件是否已 OCR 落盘？音频是否已转写落盘？
- [ ] 加密压缩包 / PDF 是否已按内置两密码尝试？失败是否报 `needs_password` 并停问用户？
- [ ] 是否先交付结构摘要并等待确认？
- [ ] `summary.md` / `meta.json` 是否已写回？
- [ ] 批量/按日粗读是否已**自动**跑 `render_rough_report` 生成 `索引/粗读-YYYY-MM-DD.html`？（未跑算出流程未完成；禁止手写整页 HTML）
- [ ] 回复是否只给了统计 + HTML 路径 + 建议深读标题？
- [ ] 回复里是否避免了全文粘贴？

## Learnings

- 本库历史产物曾用 `_pdf_txt/N_ok.txt`、`N_pypdf.txt` 等编号；新流程统一 `stem.*`，旧文件仅作只读输入。
- `付费文/_extract/imgs/` 已有页图时，优先 OCR/复用，不要无故再渲染整本 PDF。
- 本机全局曾是 Python 3.14；OCR/ASR 生态不完整。抽取环境固定用 `YOUR_DOC_ROOT/.conda/doc-read`（3.12）+ `uv pip`，勿装进全局。
- 用户 conda 的 `custom_channels.defaults` 曾指向错误 URL；创建本地环境时用 `-c conda-forge --override-channels`。
- 付费文里大量是扫描件/图片 PDF：纯文本抽取会很空，需 `--ocr`；文字层 PDF（如部分长文）可直接 `pdf-text`。
- `faster-whisper` 与 `av>=14` 不兼容（`open(..., metadata_errors=...)`）；ASR 依赖需钉死 `av>=10,<14`。
- 省 token 下一刀在「读什么」和「clean 质量」：有 summary 不读 clean；音频 clean 去套话+合并碎行通常再少 10–25% 输入。
- 单页 OCR 上 GPU 往往不赚（启动/拷贝开销）；ASR 长音频上 GPU 收益大。OCR 保持 CPU 包更合适。
- 库内常见加密附件：优先试 skill 内置两压缩密码（见「有密码的压缩包 / 加密 PDF」）；都失败再问用户，勿盲猜。
- 粗读 HTML 卡片是流程终点之一，不是可选项：批量粗读后漏跑 `render_rough_report` = 未完成。模板在 `templates/rough_scan_report.html`，只许填数据。
