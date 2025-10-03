MTG Arena Set Swapper (GUI Version)

A user-friendly application to swap the art and names of specific cards in your MTG Arena client. This is designed to replace confusing digital-only card versions (like the "Through the Omenpaths" set) with their paper counterparts.

This tool only affects your local game client. Your opponents will see the default card art and names.
⚠️ Important Warning: Terms of Service

Modifying game files is strictly against the Wizards of the Coast Terms of Service. While WotC has historically not banned players for purely cosmetic, client-side mods, using this tool is at your own risk. The developers of this script are not responsible for any actions taken against your account.

An MTG Arena update will likely undo these changes, and you will need to run the application again.
How to Use the Application

    Generate a Swap File:

        Enter a 3-letter set code into the text box (e.g., om1 for Through the Omenpaths, big for Breaking News).

        Click the "Generate swaps.json" button. The application will download the necessary card data and create a swaps.json file in the same folder.

    Apply Swaps:

        Once you have a swaps.json file, click the "Apply Swaps" button. The application will find your MTG Arena installation, back up the original files, and apply the new art and names.

    Restore Originals:

        To undo all changes, click the "Restore Originals" button. This will copy the backups and restore the game to its original state.

How to Create the One-Click Executable

To distribute this application to users who don't have Python, you need to package it into an executable.

Prerequisites:

    You must have Python 3.8+ installed on your build machine.

    You need an icon file (optional, but recommended).

        For Windows, you need an .ico file.

        For macOS, you need an .icns file.

Build Steps:

    Setup Folder: Place mtga_set_swapper_gui.py and requirements.txt in a folder. If you have an icon, place it there too.

    Install Libraries: Open a terminal or command prompt in that folder and run:

    pip install -r requirements.txt
    pip install pyinstaller

    Run the PyInstaller Command:

        For Windows (.exe):

        pyinstaller --onefile --windowed --name="MTGA Set Swapper" --icon="your_icon.ico" mtga_set_swapper_gui.py

        For macOS (.app):

        pyinstaller --onefile --windowed --name="MTGA Set Swapper" --icon="your_icon.icns" mtga_set_swapper_gui.py

    Flags Explained:

        --onefile: Bundles everything into a single executable file.

        --windowed: Prevents a black console window from appearing behind your GUI.

        --name: Sets the name of your final application.

        --icon: Attaches your custom icon to the executable.

    Distribute:

        After the command finishes, look inside the newly created dist folder.

        You will find MTGA Set Swapper.exe (on Windows) or MTGA Set Swapper.app (on macOS).

        This is your standalone application! You can zip it and share it with others. They will not need to install Python to run it.