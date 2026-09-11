@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM setup_backend.bat - PrivARcy backend environment setup
REM
REM Creates the backend folder structure, activates venv, installs
REM requirements.txt, and verifies that dlib / face_recognition /
REM FastAPI, torch/transformers, and the rest of the required packages actually import.
REM Delegates the package-install/verify logic to setup_backend.py,
REM since that script already handles the requirements.txt
REM UTF-16-vs-UTF-8 encoding trap and gives per-package diagnostics
REM that are impractical to reproduce reliably in pure batch.
REM
REM Exit codes: 0 = success, 1 = setup/venv problem, 2 = one or
REM more required packages are still missing/broken after install.
REM ============================================================

cd /d "%~dp0"

echo ========================================
echo PrivARcy Backend Setup
echo ========================================

echo.
echo Checking for venv...
if not exist "venv\Scripts\activate.bat" (
    echo   X venv\Scripts\activate.bat not found.
    echo     Create the virtual environment first, e.g.:
    echo       python -m venv venv
    goto :fail_setup
)

echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo   X Failed to activate venv.
    goto :fail_setup
)
echo   OK venv activated: %VIRTUAL_ENV%

echo.
echo Checking Python...
python --version
if errorlevel 1 (
    echo   X "python" is not available on PATH inside the venv.
    goto :fail_setup
)

echo.
echo Creating folder structure...
for %%D in (src tests models data logs temp) do (
    if not exist "%%D" (
        mkdir "%%D" 2>nul
        if exist "%%D" (echo   OK Created: %%D) else (echo   X Failed to create: %%D)
    ) else (
        echo   OK Exists: %%D
    )
)
for %%D in (src\detectors src\ocr src\classifiers src\face src\tracker src\decision src\redaction src\video src\pipeline src\workers src\config src\utils src\integration) do (
    if not exist "%%D" (
        mkdir "%%D" 2>nul
        if exist "%%D" (echo   OK Created: %%D) else (echo   X Failed to create: %%D)
    ) else (
        echo   OK Exists: %%D
    )
)

echo.
echo Checking pip...
python -m pip --version
if errorlevel 1 (
    echo   X pip is not available in this venv.
    goto :fail_setup
)

if not exist "requirements.txt" (
    echo   X requirements.txt not found in %cd%.
    goto :fail_setup
)

echo.
echo ========================================
echo Installing and verifying dependencies
echo (delegating to setup_backend.py: this
echo  also fixes a UTF-16 requirements.txt
echo  if PowerShell wrote it that way, and
echo  gives detailed dlib/face_recognition/
echo  torch/transformers diagnostics if anything fails)
echo ========================================
python setup_backend.py
set PYSETUP_RC=%ERRORLEVEL%

if %PYSETUP_RC% NEQ 0 (
    echo.
    echo ========================================
    echo Setup finished with issues (see errors above^)
    echo ========================================
    echo To activate the venv manually, run:
    echo   venv\Scripts\activate
    exit /b 2
)

echo.
echo ========================================
echo Setup complete!
echo ========================================
echo To activate the venv, run:
echo   venv\Scripts\activate
pause
exit /b 0

:fail_setup
echo.
echo ========================================
echo Setup FAILED - see error(s^) above
echo ========================================
exit /b 1
