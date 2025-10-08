# MTG Arena Set Swapper

A user-friendly application to swap the art and names of specific cards in your MTG Arena client.

---

## 🚀 How to Install and Use

1.  **Download the Application:**
    * Go to the [**Releases Page**](https://github.com/YOUR_USERNAME/YOUR_REPO/releases).
    * For **Windows**, download the `MTGA Set Swapper.exe` file.
    * For **macOS**, download the `MTGA Set Swapper.app.zip` file.

2.  **Run the Application:**
    * **On Windows:** Double-click the `.exe` file. You may get a "Windows protected your PC" popup; click "More info" and then "Run anyway".
    * **On macOS:** Unzip the file and double-click the `.app`. You may get a security warning; open "System Settings" > "Privacy & Security", scroll down, and click "Open Anyway".

3.  **Follow the In-App Instructions:**
    * Use the "Find Auto" button to locate your game installation.
    * Generate a `swaps.json` file for the sets you want to change (e.g., Source `OM1`, Target `SPM`).
    * Click "Apply Swaps" to modify the game files.
    * Click "Restore Originals" to revert all changes.

---

### ⚠️ Important Warning: Terms of Service

Modifying game files is strictly against the Wizards of the Coast Terms of Service. While WotC has historically not banned players for purely cosmetic, client-side mods, **using this tool is at your own risk**. The developers of this script are not responsible for any actions taken against your account.

An MTG Arena update will likely undo these changes, and you will need to run the application again. This tool only affects your local game client.

---

### Credits and Inspiration

This project was heavily inspired by the original **MTGA_Swapper** by **[BobJr23](https://github.com/BobJr23)**. A huge thank you for their foundational work, which provided the core logic and proof of concept. Please check out their original repository:
* [**github.com/BobJr23/MTGA_Swapper**](https://github.com/BobJr23/MTGA_Swapper)

---

### For Developers: How to Build the Executable

To package this application into a single executable file yourself:

To share this application, you can package it into a single executable file.
Prerequisites:

    Python 3.8+

    The project files organized in the following structure:

    /YourProjectFolder
    ├── app.py
    ├── requirements.txt
    ├── build_win.bat
    ├── build_mac.command
    └── /assets
        ├── icon.ico
        └── icon.icns

Build Steps (One-Click):

    For Windows:

        Make sure you have Python installed.

        Double-click build_win.bat.

    For macOS:

        Open the Terminal application.

        Navigate to your project folder (e.g., cd ~/Downloads/YourProjectFolder).

        Run this command once to make the script executable: chmod +x build_mac.command

        After that, you can simply double-click the build_mac.command file to build the application.

After the script finishes, your standalone application (MTGA Set Swapper.exe or MTGA Set Swapper.app) will be located in the dist folder.