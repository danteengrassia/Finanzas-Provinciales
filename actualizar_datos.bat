@echo off
setlocal
cd /d "%~dp0"

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 scripts\actualizar_datos.py && py -3 scripts\generar_detalle.py
  goto :resultado
)

where python >nul 2>nul
if %errorlevel% equ 0 (
  python scripts\actualizar_datos.py && python scripts\generar_detalle.py
  goto :resultado
)

if exist "%CODEX_PYTHON%" (
  "%CODEX_PYTHON%" scripts\actualizar_datos.py && "%CODEX_PYTHON%" scripts\generar_detalle.py
  goto :resultado
)

echo No se encontro Python. Instale Python 3 o ejecute la actualizacion desde Codex.
set "EXIT_CODE=1"
goto :fin

:resultado
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" echo La actualizacion termino con errores.

:fin
echo.
pause
exit /b %EXIT_CODE%
