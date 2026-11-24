# 付费文按日/按月归档工具（独立版）

把微信等下载目录里的文件，按**修改时间（下载日）**和**作者关键字**自动整理到目标文件夹。

- **当月** `YYYY-MM` 目录 → `输出/YYYY-MM-DD/付费文|未统计/`
- **往月** `YYYY-MM` 目录 → `输出/YYYY-MM/付费文|未统计/`
- 文件名命中 `authors.json` 关键字 → **付费文**，否则 → **未统计**
- 文件操作为**移动**（不是复制）

不限制文件扩展名。

---

## 环境要求

- Windows（已提供 `.bat`；Linux/macOS 可直接跑 Python）
- **Python 3.9+**（仅用标准库，无第三方依赖）

安装 Python 后，可选执行：

```bash
pip install -r requirements.txt
```

> `requirements.txt` 刻意为空依赖说明文件；装不装都不影响运行。

---

## 目录结构

```
paid_doc_archiver/
  paid_doc_archiver.py   # 主程序（单文件逻辑）
  authors.json           # 作者/付费关键字（可编辑）
  run_archive.bat        # Windows 一键运行
  requirements.txt
  README.md              # 本说明
```

---

## 快速开始

### 1. 改路径（重要）

编辑 `run_archive.bat` 顶部，或直接改 `paid_doc_archiver.py` 里的默认值：

```bat
set "SOURCE=YOUR_WECHAT_MSG_FILE"
set "OUTPUT=YOUR_DOC_ROOT"
```

示例：

```bat
set "SOURCE=D:\soft_data\Tencent\xwechat_files\<你的wxid>\msg\file"
set "OUTPUT=D:\Docs"
```

源目录典型结构：

```
msg\file\
  2026-08\     ← 往月：整月按作者分类
  2026-09\
  2026-11\     ← 当月：按每个文件的 mtime 分到日目录
```

### 2. 运行

**方式 A — 双击** `run_archive.bat`

**方式 B — 命令行**

```bash
cd paid_doc_archiver
python paid_doc_archiver.py
python paid_doc_archiver.py "D:\path\to\source" "D:\path\to\output"
```

### 3. 查看结果

输出示例：

```
YOUR_DOC_ROOT\
  2026-08\
    付费文\
    未统计\
  2026-11-19\
    付费文\
    未统计\
  paid_doc_archiver_YYYYMMDD_HHMMSS.log
```

---

## 作者关键字

编辑同目录 `authors.json`（字符串数组）。匹配规则：文件名**包含**任一关键字即算付费文；更长关键字优先，减少短词误伤。

```json
[
  "龙博认知局内容总结",
  "思投社",
  "子明",
  "付费文",
  "付费群"
]
```

改完保存后再运行即可，无需改代码。

---

## 冲突策略

| 情况 | 行为 |
|------|------|
| 目标不存在 | 移动过去 |
| 目标已存在且内容相同（size + MD5） | 删除源文件 |
| 目标已存在且内容不同 | 改名为 `原名 (1).ext` 再移动 |

---

## 注意事项

1. **会移动并可能删除源文件**，请先备份或先用小目录试跑。
2. 「当月」取运行当天的 `YYYY-MM`（系统本地时间）。
3. 空的月目录会自动跳过。
4. 日志写在**输出目录**下，便于排查。
5. 个别生僻字文件名可能导致控制台乱码，不影响实际移动（日志文件为 UTF-8）。

---

## 进阶：在代码里调用

```python
from pathlib import Path
from paid_doc_archiver import run_batch, archive_daily, rollup_monthly

run_batch(Path(r"YOUR_WECHAT_MSG_FILE"), Path(r"YOUR_DOC_ROOT"))
```

同文件还提供：

- `archive_daily` — 仅按日
- `archive_into_month` — 整月目录分类
- `rollup_monthly` — 把已有日目录扁平移入月目录

---

## 许可与免责

个人/内部分发工具。整理前请确认路径正确；因误配路径导致的数据移动，请自行负责。
