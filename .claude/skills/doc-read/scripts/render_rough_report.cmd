@echo off
setlocal
set "PY=d:\文档\.conda\doc-read\python.exe"
if not exist "%PY%" (
  echo Missing local env: %PY%
  exit /b 2
)
"%PY%" "%~dp0render_rough_report.py" %*
