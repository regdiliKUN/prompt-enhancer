@echo off
rem ============================================================================
rem  PromptEnhancer - One-click desktop shortcut creator (Windows)
rem  Same as CreateShortcut.bat; this copy uses a Chinese file name so it is
rem  easy to spot after extracting the package.
rem ============================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "EXE=%~dp0PromptEnhancer.exe"
set "HELPER=%~dp0tools\create_shortcut.py"

if exist "%EXE%" (
    echo [1/2] Application found: PromptEnhancer.exe
    echo [2/2] Creating desktop shortcut ...
    "%EXE%" --create-shortcut
    if errorlevel 1 goto FAILED
    goto DONE
)

set "PYCMD="
where py >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if not defined PYCMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
    where python3 >nul 2>nul
    if not errorlevel 1 set "PYCMD=python3"
)

if defined PYCMD (
    echo [1/2] Python found: !PYCMD!
    echo [2/2] Creating desktop shortcut ...
    rem  "%~dp0." 末尾加点，避免路径结尾的反斜杠把引号转义掉
    !PYCMD! "%HELPER%" --root "%~dp0."
    if errorlevel 1 goto FAILED
    goto DONE
)

echo.
echo [ERROR] Neither PromptEnhancer.exe nor Python was found in:
echo         %~dp0
echo         Keep this .bat inside the extracted PromptEnhancer folder,
echo         or install Python 3 and run:  python tools\create_shortcut.py
echo.
pause
exit /b 1

:FAILED
echo.
echo [ERROR] Failed to create the desktop shortcut. See the details above.
echo         A result log is written to:
echo         %%LOCALAPPDATA%%\PromptEnhancer\data\shortcut_result.log
echo.
pause
exit /b 1

:DONE
echo.
echo [OK] Done. A shortcut named "Prompt Enhancer" is on your Desktop.
echo      Double-click it to start the application.
echo.
timeout /t 6 >nul
exit /b 0
