@echo off
echo ============================================
echo   Nexo 3.0 - Build Script para Windows
echo ============================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Instala Python 3.12 desde python.org
    pause
    exit /b 1
)

REM Verificar pip
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip no encontrado.
    pause
    exit /b 1
)

echo [1/4] Instalando dependencias...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Fallo al instalar dependencias.
    pause
    exit /b 1
)

echo [2/4] Instalando PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] Fallo al instalar PyInstaller.
    pause
    exit /b 1
)

echo [3/4] Compilando Nexo 3.0...
pyinstaller --onefile --windowed --icon=assets/nexo_icono.ico --name "Nexo 3.0" --add-data "actions;actions" --add-data "assets;assets" --add-data "config;config" --add-data "core;core" --add-data "launchers;launchers" --add-data "memory;memory" --add-data "requirements.txt;." main.py
if %errorlevel% neq 0 (
    echo [ERROR] Fallo la compilacion.
    pause
    exit /b 1
)

echo [4/4] Compilacion exitosa!
echo.
echo El ejecutable se encuentra en: dist/Nexo 3.0.exe
echo.
echo IMPORTANTE: No olvides copiar la carpeta config/api_keys.json.example
echo como config/api_keys.json y poner tu API key de Gemini.
echo.
pause
