@echo off
REM Encoding: GBK/CP936 + CRLF (Chinese Windows cmd).
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM  文档库一键工具：分类归档 / 文档抽取
REM  回车 = 使用默认路径；输入路径可临时覆盖
REM ============================================================

cd /d "%~dp0"
if errorlevel 1 (
  echo [ERROR] 无法进入仓库根目录: %~dp0
  pause
  exit /b 1
)

set "REPO_ROOT=%CD%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if defined DOC_READ_PYTHON (
  set "PY_BOOT=%DOC_READ_PYTHON%"
) else if exist "%REPO_ROOT%\.conda\doc-read\python.exe" (
  set "PY_BOOT=%REPO_ROOT%\.conda\doc-read\python.exe"
) else (
  set "PY_BOOT=python"
)

call :load_dotenv "%REPO_ROOT%\.env.local"

if not defined DOC_READ_ROOT set "DOC_READ_ROOT=%REPO_ROOT%"
if not defined DOC_LOCAL_ROOT set "DOC_LOCAL_ROOT=%DOC_READ_ROOT%\local"

if defined WECHAT_MSG_FILE (
  set "DEF_ARCHIVE_SRC=%WECHAT_MSG_FILE%"
) else (
  set "DEF_ARCHIVE_SRC="
)
set "DEF_ARCHIVE_OUT=%DOC_LOCAL_ROOT%"

call :today_parts
set "DEF_EXTRACT_SRC=%DOC_LOCAL_ROOT%\%TODAY_YM%\%TODAY_DD%\付费文"

if defined DOC_READ_PYTHON (
  set "PY_EXTRACT=%DOC_READ_PYTHON%"
) else (
  set "PY_EXTRACT=%DOC_READ_ROOT%\.conda\doc-read\python.exe"
)
set "PY_ARCHIVE=%PY_EXTRACT%"
if not exist "%PY_ARCHIVE%" (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%P in ('where python') do (
      set "PY_ARCHIVE=%%P"
      goto :py_archive_done
    )
  )
)
:py_archive_done

set "ARCHIVER_PY=%REPO_ROOT%\tools\paid_doc_archiver\paid_doc_archiver.py"
set "EXTRACT_PY=%REPO_ROOT%\.claude\skills\doc-read\scripts\extract_docs.py"
if not exist "%EXTRACT_PY%" set "EXTRACT_PY=%REPO_ROOT%\tools\.claude\skills\doc-read\scripts\extract_docs.py"

:menu
cls
echo.
echo ===== 文档库一键工具 =====
echo 仓库: %REPO_ROOT%
echo.
echo   1. 文档分类归档  ^(微信下载 -^> local^)
echo   2. 文档抽取转换  ^(源文件 -^> 源旁 _extract^)
echo   3. 环境检测      ^(Python / OCR / ASR / CUDA^)
echo   0. 退出
echo.
set "CHOICE="
set /p "CHOICE=请选择 [0-3]: "
if "%CHOICE%"=="1" goto do_archive
if "%CHOICE%"=="2" goto do_extract
if "%CHOICE%"=="3" goto do_check
if "%CHOICE%"=="0" goto bye
if /i "%CHOICE%"=="q" goto bye
echo 无效选择。
timeout.exe /t 1 /nobreak >nul
goto menu

:do_archive
echo.
echo ----- 文档分类归档 -----
if defined DEF_ARCHIVE_SRC (
  echo 默认源: %DEF_ARCHIVE_SRC%
) else (
  echo 默认源: ^(未设置 WECHAT_MSG_FILE，请手动输入^)
)
echo 默认输出: %DEF_ARCHIVE_OUT%
echo.

set "SRC="
set /p "SRC=源路径 [回车=默认]: "
if not defined SRC set "SRC=%DEF_ARCHIVE_SRC%"

set "OUT="
set /p "OUT=输出路径 [回车=默认]: "
if not defined OUT set "OUT=%DEF_ARCHIVE_OUT%"

if not defined SRC (
  echo [ERROR] 没有源路径。请设置 WECHAT_MSG_FILE，或在上方输入。
  goto end_pause
)
if not exist "%ARCHIVER_PY%" (
  echo [ERROR] 找不到归档脚本: %ARCHIVER_PY%
  goto end_pause
)
if not exist "%PY_ARCHIVE%" (
  echo [ERROR] 找不到 Python: %PY_ARCHIVE%
  echo 请安装 Python 3.9+，或设置 DOC_READ_PYTHON。
  goto end_pause
)
if not exist "%SRC%\" if not exist "%SRC%" (
  echo [ERROR] 源路径不存在: %SRC%
  goto end_pause
)

echo.
echo 执行归档...
echo SRC=%SRC%
echo OUT=%OUT%
echo.

"%PY_ARCHIVE%" "%ARCHIVER_PY%" "%SRC%" "%OUT%"
set "ERR=!ERRORLEVEL!"
echo.
if not "!ERR!"=="0" echo 结束，exit=!ERR!。日志一般在输出目录下。
if "!ERR!"=="0" echo 完成。
goto end_pause

:do_extract
echo.
echo ----- 文档抽取转换 -----
echo 产物固定写在源旁 _extract 目录，无独立输出目录。
echo 默认源: %DEF_EXTRACT_SRC%
echo.

set "SRC="
set /p "SRC=源路径(文件或文件夹) [回车=默认]: "
if not defined SRC set "SRC=%DEF_EXTRACT_SRC%"

set "GLOB="
set /p "GLOB=文件过滤 glob [回车=全部支持格式，例 *.pdf]: "

echo.
echo 选项 ^(可多选，如 oa / of ；回车=不加开关^):
echo   o = --ocr    ^(扫描件 OCR^)
echo   a = --asr    ^(音频转写^)
echo   f = --force  ^(已有 raw 也重抽^)
set "OPTS="
set /p "OPTS=选项: "
if not defined OPTS set "OPTS="

set "FLAG_OCR="
set "FLAG_ASR="
set "FLAG_FORCE="
if not "!OPTS!"=="!OPTS:o=!" set "FLAG_OCR=--ocr"
if not "!OPTS!"=="!OPTS:O=!" set "FLAG_OCR=--ocr"
if not "!OPTS!"=="!OPTS:a=!" set "FLAG_ASR=--asr"
if not "!OPTS!"=="!OPTS:A=!" set "FLAG_ASR=--asr"
if not "!OPTS!"=="!OPTS:f=!" set "FLAG_FORCE=--force"
if not "!OPTS!"=="!OPTS:F=!" set "FLAG_FORCE=--force"

if not exist "%EXTRACT_PY%" (
  echo [ERROR] 找不到抽取脚本: %EXTRACT_PY%
  goto end_pause
)
if not exist "%PY_EXTRACT%" (
  echo [ERROR] 找不到抽取环境: %PY_EXTRACT%
  echo 请设置 DOC_READ_PYTHON，或创建 .conda\doc-read ^(见 tools\README.md^)。
  goto end_pause
)
if not exist "%SRC%\" if not exist "%SRC%" (
  echo [ERROR] 源路径不存在: %SRC%
  goto end_pause
)

echo.
echo 执行抽取...
echo SRC=%SRC%
if defined GLOB echo GLOB=%GLOB%
if defined FLAG_OCR echo use %FLAG_OCR%
if defined FLAG_ASR echo use %FLAG_ASR%
if defined FLAG_FORCE echo use %FLAG_FORCE%
echo.

if defined GLOB goto extract_with_glob
"%PY_EXTRACT%" "%EXTRACT_PY%" "%SRC%" %FLAG_OCR% %FLAG_ASR% %FLAG_FORCE%
goto extract_after

:extract_with_glob
"%PY_EXTRACT%" "%EXTRACT_PY%" "%SRC%" --glob "%GLOB%" %FLAG_OCR% %FLAG_ASR% %FLAG_FORCE%

:extract_after
set "ERR=!ERRORLEVEL!"
echo.
if not "!ERR!"=="0" echo 结束，exit=!ERR!。
if "!ERR!"=="0" echo 完成。请查看源旁 _extract 目录。
goto end_pause

:do_check
echo.
echo ----- 环境检测 -----
if not exist "%EXTRACT_PY%" (
  echo [ERROR] 找不到抽取脚本: %EXTRACT_PY%
  goto end_pause
)
if not exist "%PY_EXTRACT%" (
  echo [ERROR] 找不到 Python: %PY_EXTRACT%
  echo 请设置 DOC_READ_PYTHON，或创建 .conda\doc-read ^(见 tools\README.md^)。
  goto end_pause
)
echo.
set "PYTHONIOENCODING=gbk"
"%PY_EXTRACT%" "%EXTRACT_PY%" --check-env
set "PYTHONIOENCODING=utf-8"
set "ERR=!ERRORLEVEL!"
echo.
if not "!ERR!"=="0" echo 环境检测未通过 ^(exit=!ERR!^)。
if "!ERR!"=="0" echo 环境检测通过。
goto end_pause

:end_pause
echo.
echo 按回车返回菜单...
pause >nul
goto menu

:bye
echo 再见.
endlocal
exit /b 0

:today_parts
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM"') do set "TODAY_YM=%%I"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format dd"') do set "TODAY_DD=%%I"
if not defined TODAY_YM set "TODAY_YM=2026-11"
if not defined TODAY_DD set "TODAY_DD=25"
exit /b 0

:load_dotenv
if not exist "%~1" exit /b 0
set "_ENV_TMP=%TEMP%\doc_read_env_%RANDOM%.bat"
"%PY_BOOT%" "%REPO_ROOT%\scripts\load_dotenv_bat.py" "%~1" "%_ENV_TMP%"
if errorlevel 1 (
  echo [WARN] 加载 .env.local 失败，继续用内置默认。
  set "_ENV_TMP="
  exit /b 0
)
if exist "%_ENV_TMP%" (
  call "%_ENV_TMP%"
  del "%_ENV_TMP%" >nul 2>&1
)
set "_ENV_TMP="
exit /b 0
