@echo off
setlocal
if defined DOC_READ_PYTHON (
  set "PY=%DOC_READ_PYTHON%"
) else (
  set "PY=YOUR_DOC_ROOT\.conda\doc-read\python.exe"
)
if not exist "%PY%" (
  echo Missing local env: %PY%
  echo Set DOC_READ_PYTHON, or replace YOUR_DOC_ROOT with your doc library path.
  exit /b 2
)
"%PY%" "%~dp0render_rough_report.py" %*
