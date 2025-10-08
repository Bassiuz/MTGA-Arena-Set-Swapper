@echo off
echo ===================================
echo  MTGA Set Swapper - Windows Build
echo ===================================
echo.

echo [1/4] Checking for Python...
python --version 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.8+ and add it to your PATH.
    pause
    exit /b 1
)
echo Python found.
echo.

echo [2/4] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo.

echo [3/4] Installing required libraries...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install libraries. Check requirements.txt.
    pause
    exit /b 1
)
echo.

echo [4/4] Building the application with PyInstaller...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name="MTGA Set Swapper" ^
    --icon="assets/icon.ico" ^
    --additional-hooks-dir=./hooks ^
    app.py

if %errorlevel% neq 0 (
    echo ERROR: PyInstaller failed to build the application.
    pause
    exit /b 1
)
echo.

deactivate

echo ===================================
echo  Build Complete!
echo ===================================
echo Your application (.exe) can be found in the 'dist' folder.
echo.
pause