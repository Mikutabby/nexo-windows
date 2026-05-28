@echo off
title NEXO Beta - DEBUG
cd /d "%~dp0"
echo ============================================
echo  J.A.R.V.I.S Beta - Modo Diagnostico
echo ============================================
echo  Directorio: %CD%
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual .venv
    echo Ejecuta NEXO_Beta_Installer.exe nuevamente.
    pause & exit /b 1
)
if not exist "main.py" (
    echo [ERROR] No se encontro main.py en %CD%
    pause & exit /b 1
)
echo [OK] Iniciando NEXO Beta con salida de debug...
echo.
.venv\Scripts\python.exe main.py
echo.
echo ============================================
echo  NEXO se cerro. Codigo: %ERRORLEVEL%
echo ============================================
pause
