@echo off
title NEXO Beta - Desinstalador
echo ============================================
echo  J.A.R.V.I.S Beta - Desinstalador
echo ============================================
echo.
set "NEXO_DIR=%~dp0"
set "NEXO_DIR=%NEXO_DIR:~0,-1%"
set "SHORTCUT=%USERPROFILE%\Desktop\NEXO Beta.lnk"
echo Directorio: %NEXO_DIR%
echo.
echo Quitando proteccion de archivos...
icacls "%NEXO_DIR%" /reset /t /c /q
attrib -r -s -h "%NEXO_DIR%\*" /s /d
echo Eliminando acceso directo del escritorio...
if exist "%SHORTCUT%" del /f /q "%SHORTCUT%"
echo Eliminando NEXO Beta...
cd /d "%USERPROFILE%"
rd /s /q "%NEXO_DIR%"
echo.
if not exist "%NEXO_DIR%" (
    echo NEXO Beta desinstalado correctamente.
) else (
    echo [WARN] Algunos archivos no se pudieron eliminar.
    echo Intentalo de nuevo como Administrador.
)
pause
