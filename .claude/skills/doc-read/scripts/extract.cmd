@echo off
setlocal
set "PY=d:\文档\.conda\doc-read\python.exe"
if not exist "%PY%" (
  echo Missing local env: %PY%
  echo Create with: conda create -y -p "d:\文档\.conda\doc-read" python=3.12 -c conda-forge --override-channels
  echo Then: uv pip install --python "%PY%" -r "%~dp0requirements.txt"
  exit /b 2
)
"%PY%" "%~dp0extract_docs.py" %*
