@echo off
REM Gera dist\AnalisadorAcoes.exe (um único arquivo, sem janela de console).
REM Requer Python 3.10+ instalado (marque "Add python.exe to PATH" na instalação).
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv || goto :erro
)
call .venv\Scripts\activate.bat || goto :erro
python -m pip install --upgrade pip || goto :erro
pip install -r requirements-build.txt || goto :erro

pyinstaller --noconfirm --clean --onefile --windowed --name AnalisadorAcoes main.py || goto :erro

echo.
echo Pronto! Executavel em: %~dp0dist\AnalisadorAcoes.exe
pause
exit /b 0

:erro
echo.
echo Ocorreu um erro na geracao do executavel.
pause
exit /b 1
