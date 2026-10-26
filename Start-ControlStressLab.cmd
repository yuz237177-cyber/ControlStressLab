@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\v1.0.0\ControlStressLab\ControlStressLab.exe" (
  start "" "%~dp0dist\v1.0.0\ControlStressLab\ControlStressLab.exe" --workspace "%~dp0outputs\gui" %*
  exit /b
)
set "CSL_RUNTIME=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python"
if exist "%CSL_RUNTIME%\pythonw.exe" (
  start "" "%CSL_RUNTIME%\pythonw.exe" "%~dp0run_gui.py"
  exit /b
)
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0run_gui.py"
  exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0run_gui.py"
  exit /b
)
echo Python 3.10+ is required. See docs/GUI_GUIDE.md.
pause
