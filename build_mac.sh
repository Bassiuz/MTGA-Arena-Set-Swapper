#!/bin/bash

echo "==================================="
echo " MTGA Set Swapper - macOS Build"
echo "==================================="
echo ""

# Check for Python 3
echo "[1/4] Checking for Python 3..."
if ! command -v python3 &> /dev/null
then
    echo "ERROR: Python 3 could not be found."
    echo "Please install Python 3.8+ and try again."
    exit 1
fi
echo "Python 3 found."
echo ""

# Create virtual environment
echo "[2/4] Creating virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment."
    exit 1
fi
source venv/bin/activate
echo ""

# Install requirements
echo "[3/4] Installing required libraries..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install libraries. Check requirements.txt."
    exit 1
fi
echo ""

# Run PyInstaller
echo "[4/4] Building the application with PyInstaller..."
pyinstaller \
    --onefile \
    --windowed \
    --name="MTGA Set Swapper" \
    --icon="assets/icon.icns" \
    --additional-hooks-dir=./hooks \
    app.py

if [ $? -ne 0 ]; then
    echo "ERROR: PyInstaller failed to build the application."
    exit 1
fi
echo ""

deactivate

echo "==================================="
echo " Build Complete!"
echo "==================================="
echo "Your application (.app) can be found in the 'dist' folder."
echo ""