@echo off
setlocal
REM Prefer DOC_READ_PYTHON, else D:\文档\doc-read-toolkit\.conda\doc-read\python.exe
if defined DOC_READ_PYTHON (
  set "PY=%DOC_READ_PYTHON%"
) else (
  set "PY=D:\文档\doc-read-toolkit\.conda\doc-read\python.exe"
)
if not exist "%PY%" (
  echo Missing local env: %PY%
  echo Set DOC_READ_PYTHON, or replace D:/文档/doc-read-toolkit with your doc library path.
  echo Create with: conda create -y -p "D:/文档/doc-read-toolkit\.conda\doc-read" python=3.12 -c conda-forge --override-channels
  echo Then: uv pip install --python "%PY%" -r "%~dp0requirements.txt"
  exit /b 2
)
"%PY%" "%~dp0extract_docs.py" %*
