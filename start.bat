@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "Samira Faria - Servidor" cmd /k "py -3 app.py"
) else (
  start "Samira Faria - Servidor" cmd /k "python app.py"
)
timeout /t 3 >nul
start "" "http://127.0.0.1:8080"
echo Site aberto no navegador. Mantenha a janela do servidor aberta.
pause
