# hooks/hook-tkinter.py
import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# This hook is necessary to correctly bundle the Tcl/Tk libraries on macOS for Tkinter.
if sys.platform == 'darwin':
    # Get the base paths for Tcl and Tk libraries from Python's _tkinter module.
    # This is a more reliable way to find the correct versions.
    import _tkinter
    tcl_dir = os.path.dirname(_tkinter.TCL_TK_CACHE_PATH)
    
    # Define the Tcl and Tk library folder names.
    tcl_lib_name = f'tcl{_tkinter.TCL_VERSION}'
    tk_lib_name = f'tk{_tkinter.TK_VERSION}'
    
    # Collect all files from the Tcl and Tk library directories.
    datas = collect_data_files(os.path.join(tcl_dir, tcl_lib_name))
    datas += collect_data_files(os.path.join(tcl_dir, tk_lib_name))