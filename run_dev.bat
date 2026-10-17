@echo off
REM Executa o programa em modo de desenvolvimento (sem gerar .exe).
setlocal
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv || goto :erro )
call .venv\Scripts\activate.bat || goto :erro
pip install -r requirements.txt || goto :erro
python main.py
exit /b 0
:erro
pause
exit /b 1
