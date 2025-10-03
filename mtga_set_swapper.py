import platform
import shutil
import sqlite3
import time
import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
import UnityPy

# Import Tkinter for the GUI
import tkinter as tk
from tkinter import ttk, scrolledtext, font

# --- Helper Functions (unchanged from original script) ---

def find_mtga_path() -> Optional[Path]:
    """Automatically detects the MTG Arena installation path for Windows and macOS."""
    system = platform.system()
    home = Path.home()
    
    if system == "Windows":
        paths_to_check = [
            Path("C:/Program Files/Wizards of the Coast/MTGA"),
            Path("C:/Program Files (x86)/Wizards of the Coast/MTGA"),
            home / "AppData/Local/Wizards of the Coast/MTGA",
            Path("C:/Program Files/Epic Games/MagicTheGathering"),
        ]
    elif system == "Darwin": # macOS
        paths_to_check = [
            Path("/Applications/MTGA.app"),
            home / "Library/Application Support/com.wizards.mtga",
            home / "Applications/MTGA.app",
            Path("/Applications/Epic Games/MagicTheGathering/MTGA.app")
        ]
    else:
        print(f"Unsupported OS: {system}. Please manually locate the MTGA path.")
        return None

    print("🔍 Searching for MTG Arena installation...")
    for path in paths_to_check:
        data_path_check = path / "Contents/Resources/Data" if system == "Darwin" else path / "MTGA_Data"
        if path.exists() and data_path_check.exists():
            print(f"✅ MTG Arena found at: {path}")
            return path
    
    print("❌ Could not automatically find MTG Arena installation.")
    print("Please ensure the game is installed in a standard location.")
    return None

def get_card_data_from_url(scryfall_url: str) -> Optional[Dict]:
    """Fetches card data from Scryfall API using a full card URL."""
    try:
        parts = scryfall_url.split('/')
        set_code = parts[-3]
        collector_number = parts[-2].split('?')[0]
        
        api_url = f"https://api.scryfall.com/cards/{set_code}/{collector_number}"
        response = requests.get(api_url)
        response.raise_for_status()
        time.sleep(0.1) # Be polite to the API
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching card data for {scryfall_url}: {e}")
        return None
    except IndexError:
        print(f"❌ Invalid Scryfall URL format: {scryfall_url}")
        return None

def download_image(url: str, dest_path: Path) -> bool:
    """Downloads an image from a URL to a destination path."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error downloading image {url}: {e}")
        return False

def get_data_path(mtga_path: Path) -> Path:
    """Gets the correct MTGA_Data path for Windows or macOS."""
    if platform.system() == "Darwin":
        return mtga_path / "Contents/Resources/Data"
    return mtga_path / "MTGA_Data"

def get_mtga_database(data_path: Path) -> Optional[Path]:
    """Finds the main SQLite database for MTG Arena."""
    db_path = data_path / "Downloads/Data"
    if not db_path.exists():
        print(f"❌ Database directory not found at: {db_path}")
        return None
    db_files = list(db_path.glob("data_cards_*.mtga"))
    if not db_files:
        print("❌ Could not find MTGA card database file.")
        return None
    return max(db_files, key=os.path.getmtime)
    
def get_card_ids_from_db(db_path: Path, card_names: List[str]) -> Dict[str, int]:
    """Retrieves the MTGA internal card IDs (Grpid) for a list of card names."""
    card_ids = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    loc_db_path_list = list(Path(db_path.parent).glob("data_loc_*.mtga"))
    if not loc_db_path_list:
        print("❌ Could not find localization database.")
        conn.close()
        return {}
    loc_db_path = max(loc_db_path_list, key=os.path.getmtime)
    conn.execute(f"ATTACH DATABASE '{loc_db_path}' as loc")

    query = f"""
    SELECT c.grpid, l.enUS
    FROM cards c
    JOIN localizations l ON c.titleId = l.locId
    WHERE l.enUS IN ({','.join('?' * len(card_names))})
    """

    try:
        cursor.execute(query, card_names)
        results = cursor.fetchall()
        for grpid, name in results:
            card_ids[name] = grpid
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
    finally:
        conn.close()
        
    return card_ids

def find_asset_bundles(data_path: Path, card_id: int) -> Tuple[Optional[Path], Optional[Path]]:
    """Finds the asset bundles containing a card's art and data."""
    asset_dir = data_path / "Downloads/AssetBundle"
    card_art_bundle, cards_bundle = None, None
    
    for bundle in asset_dir.glob("cardart_*.bundle"):
        try:
            parts = bundle.stem.split('_')
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                if int(parts[1]) <= card_id <= int(parts[2]):
                    card_art_bundle = bundle
                    break
        except (ValueError, IndexError): continue
            
    for bundle in asset_dir.glob("cards_*.bundle"):
        try:
            parts = bundle.stem.split('_')
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                if int(parts[1]) <= card_id <= int(parts[2]):
                    cards_bundle = bundle
                    break
        except (ValueError, IndexError): continue
            
    return card_art_bundle, cards_bundle

# --- Core Logic Functions ---

def generate_swap_file(set_code: str):
    print(f"\n--- Generating swap file for set: {set_code.upper()} ---")
    all_cards, swaps_to_generate = [], []
    next_page_url = f"https://api.scryfall.com/cards/search?q=set:{set_code}"
    
    print("Fetching card data from Scryfall...")
    while next_page_url:
        try:
            response = requests.get(next_page_url)
            response.raise_for_status()
            data = response.json()
            all_cards.extend(data.get('data', []))
            next_page_url = data.get('next_page')
            time.sleep(0.1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching data from Scryfall: {e}")
            return

    for card in all_cards:
        if 'printed_name' in card and 'scryfall_uri' in card:
            clean_url = card['scryfall_uri'].split('?')[0]
            swaps_to_generate.append({"source_card_name": card['printed_name'], "target_scryfall_url": clean_url})
            
    if not swaps_to_generate:
        print(f"ℹ️ No cards with alternate 'printed_name' found in set {set_code.upper()}.")
        return

    swaps_to_generate.sort(key=lambda x: x['source_card_name'])
    try:
        with open("swaps.json", "w") as f:
            json.dump(swaps_to_generate, f, indent=2)
        print(f"\n✅ Successfully generated `swaps.json` with {len(swaps_to_generate)} entries.")
    except IOError as e:
        print(f"❌ Error writing to `swaps.json`: {e}")

def perform_swap():
    print("\n--- Starting Card Swap Process ---")
    mtga_path = find_mtga_path()
    if not mtga_path: return
    data_path = get_data_path(mtga_path)
    
    try:
        with open("swaps.json", "r") as f: swaps_config = json.load(f)
    except FileNotFoundError:
        print("❌ `swaps.json` not found! Please generate it first."); return
    except json.JSONDecodeError:
        print("❌ `swaps.json` is not valid JSON. Please check its syntax."); return

    db_path = get_mtga_database(data_path)
    if not db_path: return
        
    source_names = [swap['source_card_name'] for swap in swaps_config]
    print(f"\n🔍 Finding Arena IDs for {len(source_names)} cards...")
    card_id_map = get_card_ids_from_db(db_path, source_names)
    
    missing_cards = set(source_names) - set(card_id_map.keys())
    if missing_cards: print(f"⚠️ Could not find in database: {', '.join(missing_cards)}")

    temp_dir = Path("./temp_art"); backup_dir = data_path / "Downloads/AssetBundle_Backup"
    temp_dir.mkdir(exist_ok=True); backup_dir.mkdir(exist_ok=True)
    
    print("\nProcessing swaps...")
    for swap in swaps_config:
        source_name = swap['source_card_name']
        if source_name not in card_id_map: continue
            
        card_id = card_id_map[source_name]
        print(f"\nProcessing swap for '{source_name}' (ID: {card_id})")

        target_data = get_card_data_from_url(swap['target_scryfall_url'])
        if not target_data: print(f"   Skipping '{source_name}' due to API error."); continue
            
        target_name = target_data.get('name', source_name)
        image_url = target_data.get('image_uris', {}).get('art_crop')
        
        if not image_url: print(f"   Could not find art for '{target_name}'. Skipping."); continue
        
        image_path = temp_dir / f"{card_id}.jpg"
        if not download_image(image_url, image_path): print(f"   Failed to download art for '{target_name}'. Skipping."); continue

        art_bundle_path, cards_bundle_path = find_asset_bundles(data_path, card_id)
        if not all([art_bundle_path, cards_bundle_path]): print(f"   ❌ Could not locate asset bundles for '{source_name}'. Skipping."); continue

        for bundle_path in [art_bundle_path, cards_bundle_path]:
            if not (backup_dir / bundle_path.name).exists():
                shutil.copy(bundle_path, backup_dir)
                print(f"      - Backed up {bundle_path.name}")
        
        env_art = UnityPy.load(str(art_bundle_path))
        for obj in env_art.objects:
            if obj.type.name == "Texture2D" and obj.read().name == f"Card_Art_{card_id}":
                texture = obj.read(); texture.image = image_path.read_bytes(); texture.save()
                with open(art_bundle_path, "wb") as f: f.write(env_art.file.save())
                print(f"   -> Art replaced in: {art_bundle_path.name}"); break

        env_cards = UnityPy.load(str(cards_bundle_path))
        for obj in env_cards.objects:
            if obj.type.name == "TextAsset" and obj.read().name == f"Card_Title_{card_id}":
                text_asset = obj.read(); text_asset.text = target_name; text_asset.save()
                with open(cards_bundle_path, "wb") as f: f.write(env_cards.file.save())
                print(f"   -> Name replaced in: {cards_bundle_path.name}"); break

    shutil.rmtree(temp_dir)
    print("\n--- ✅ Swap Process Complete! ---")
    print("Launch MTG Arena to see your changes.")

def restore_backups():
    print("\n--- Restoring Original Game Files ---")
    mtga_path = find_mtga_path()
    if not mtga_path: return
    data_path = get_data_path(mtga_path)
    
    asset_dir = data_path / "Downloads/AssetBundle"
    backup_dir = data_path / "Downloads/AssetBundle_Backup"
    
    if not backup_dir.exists() or not any(backup_dir.iterdir()):
        print("ℹ️ No backups found. Nothing to restore."); return
        
    backups = list(backup_dir.glob("*.bundle"))
    print(f"Found {len(backups)} files to restore.")
    for backup_file in backups: shutil.copy(backup_file, asset_dir / backup_file.name)

    print("\n--- ✅ Restore Complete! ---")
    print("Your game files have been returned to their original state.")

# --- GUI Application using Tkinter ---

class StdoutRedirector:
    """A helper class to redirect stdout to a Tkinter Text widget."""
    def __init__(self, text_widget):
        self.text_space = text_widget
        self.text_space.see("end")

    def write(self, string):
        self.text_space.configure(state='normal')
        self.text_space.insert('end', string)
        self.text_space.see('end')
        self.text_space.configure(state='disabled')

    def flush(self):
        pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Arena Set Swapper")
        self.geometry("650x550")
        self.resizable(False, False)
        
        self.create_widgets()
        
        # Redirect stdout to the log widget
        sys.stdout = StdoutRedirector(self.log_widget)
        sys.stderr = StdoutRedirector(self.log_widget)
        
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # --- Fonts ---
        title_font = font.Font(family="Helvetica", size=20, weight="bold")
        subtitle_font = font.Font(family="Helvetica", size=11)
        
        # --- Header ---
        ttk.Label(main_frame, text="MTG Arena Set Swapper", font=title_font).pack(pady=(0, 5))
        ttk.Label(main_frame, text="A tool to replace digital-only card art and names.", font=subtitle_font).pack(pady=(0, 10))

        # --- Log Viewer ---
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill="both", expand=True, pady=5)
        self.log_widget = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', bg="black", fg="white", font=("Courier New", 10))
        self.log_widget.pack(fill="both", expand=True)
        
        # --- Controls ---
        controls_frame = ttk.Frame(main_frame)
        controls_frame.pack(fill="x", pady=10)
        
        # Generate Controls
        gen_frame = ttk.Frame(controls_frame)
        gen_frame.pack(fill="x", pady=5)
        ttk.Label(gen_frame, text="Enter 3-Letter Set Code:").pack(side="left", padx=(0, 5))
        self.set_code_entry = ttk.Entry(gen_frame, width=10)
        self.set_code_entry.insert(0, "om1")
        self.set_code_entry.pack(side="left", padx=5)
        self.generate_button = ttk.Button(gen_frame, text="Generate swaps.json", command=lambda: self.run_in_thread(generate_swap_file, self.set_code_entry.get()))
        self.generate_button.pack(side="left", padx=5)

        # Action Buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill="x", pady=10)
        
        self.swap_button = ttk.Button(action_frame, text="Apply Swaps", command=lambda: self.run_in_thread(perform_swap))
        self.swap_button.pack(side="left", expand=True, fill="x", padx=5)

        self.restore_button = ttk.Button(action_frame, text="Restore Originals", command=lambda: self.run_in_thread(restore_backups))
        self.restore_button.pack(side="left", expand=True, fill="x", padx=5)
        
        self.exit_button = ttk.Button(action_frame, text="Exit", command=self.destroy)
        self.exit_button.pack(side="left", expand=True, fill="x", padx=5)

    def run_in_thread(self, target_func, *args):
        """Runs a function in a separate thread to keep the GUI responsive."""
        self.set_buttons_state('disabled')
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()
        self.monitor_thread(thread)

    def monitor_thread(self, thread):
        """Checks if the thread is still running and re-enables buttons when it's done."""
        if thread.is_alive():
            self.after(100, lambda: self.monitor_thread(thread))
        else:
            self.set_buttons_state('normal')

    def set_buttons_state(self, state):
        """Disables or enables all interactive buttons."""
        self.generate_button.config(state=state)
        self.swap_button.config(state=state)
        self.restore_button.config(state=state)
        self.exit_button.config(state=state)

if __name__ == "__main__":
    app = App()
    app.mainloop()

