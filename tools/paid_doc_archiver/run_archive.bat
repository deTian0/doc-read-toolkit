@echo off
chcp 65001 >nul
setlocal EnableExtensions

REM Edit these two paths before first run (or set WECHAT_MSG_FILE / DOC_LOCAL_ROOT):
if defined WECHAT_MSG_FILE (set "SOURCE=%WECHAT_MSG_FILE%") else (set "SOURCE=YOUR_WECHAT_MSG_FILE")
if defined DOC_LOCAL_ROOT (set "OUTPUT=%DOC_LOCAL_ROOT%") else (set "OUTPUT=YOUR_DOC_ROOT\local")

cd /d "%~dp0" || (
  echo [ERROR] cannot cd to script folder
  pause
  exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo.
echo ===== Paid-doc one-click archive =====
echo SOURCE: %SOURCE%
echo OUTPUT: %OUTPUT%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found in PATH. Install Python 3.9+ and retry.
  pause
  exit /b 1
)

python paid_doc_archiver.py "%SOURCE%" "%OUTPUT%"
set "ERR=%ERRORLEVEL%"

echo.
if "%ERR%"=="0" (
  echo Done.
) else (
  echo Finished with failures, exit=%ERR%. See logs under OUTPUT.
)
echo.
pause
exit /b %ERR%
