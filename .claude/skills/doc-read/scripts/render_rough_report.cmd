@echo off
setlocal
if defined DOC_READ_PYTHON (
  set "PY=%DOC_READ_PYTHON%"
) else (
  set "PY=D:\文档\.conda\doc-read\python.exe"
)
if not exist "%PY%" (
  echo Missing local env: %PY%
  echo Set DOC_READ_PYTHON, or replace D:/文档 with your doc library path.
  exit /b 2
)
"%PY%" "%~dp0render_rough_report.py" %*
