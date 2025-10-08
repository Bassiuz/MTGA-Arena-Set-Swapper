# hooks/hook-UnityPy.py
from PyInstaller.utils.hooks import collect_data_files

# Collect all data files from the UnityPy.resources package
datas = collect_data_files('UnityPy.resources')

# Define the hidden import as a simple list of strings
hiddenimports = ['UnityPy.resources']