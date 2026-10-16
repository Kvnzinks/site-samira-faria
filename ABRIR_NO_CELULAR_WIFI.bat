@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "HOST=0.0.0.0"
set "PORT=8080"
set "PYRUN="
where py >nul 2>nul
if not errorlevel 1 (
  py -3.13 -c "import sys;sys.exit(0)" >nul 2>nul
  if not errorlevel 1 set "PYRUN=py -3.13"
)
if not defined PYRUN (
  where python >nul 2>nul
  if not errorlevel 1 set "PYRUN=python"
)
if not defined PYRUN (
  echo ERRO: Python nao encontrado. Instale Python 3.13.
  pause
  exit /b 1
)
echo.
echo ======================================================
echo SAMIRA FARIA - ABRIR NO CELULAR PELA MESMA REDE WI-FI
echo ======================================================
echo.
echo 1. Conecte computador e celular a mesma rede Wi-Fi.
echo 2. Mantenha esta janela aberta e o computador ligado.
echo 3. No celular, entre em http://IP_DO_COMPUTADOR:8080
echo.
echo IPv4 do computador:
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notmatch 'vEthernet|Virtual|WSL|VPN' } | Select-Object -ExpandProperty IPAddress" 
echo.
echo Quando o Windows Firewall perguntar, permita em REDES PRIVADAS.
echo Abrindo servidor...
echo.
%PYRUN% app.py
if errorlevel 1 echo Ocorreu erro na inicializacao.
pause
