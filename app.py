import platform
import shutil
import sqlite3
import time
import json
import os
import sys
import threading
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
import UnityPy
from PIL import Image

# Import Tkinter for the GUI
import tkinter as tk
from tkinter import ttk, scrolledtext, font, filedialog, messagebox

# Configure UnityPy with a fallback version. This will be updated by auto-detection.
UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.42f1"

# --- Helper Functions ---

def configure_unity_version(data_path: Path):
    """
    Detects and configures the Unity version from the game's level0 file.
    This uses a direct slicing method which is more reliable for MTGA.
    """
    try:
        level0_path = data_path / "level0"
        if level0_path.exists():
            with open(level0_path, "rb") as f:
                # The version string is known to be in this byte range
                version_text = f.read().decode("latin-1").strip()[40:60].replace("\x00", "")
                if re.match(r"20\d{2}\.\d+\.\d+f\d+", version_text):
                    UnityPy.config.FALLBACK_UNITY_VERSION = version_text
                    print(f"✅ Automatically configured Unity version to: {version_text}")
                else:
                    print(f"⚠️ Could not parse Unity version from level0 file. Using fallback.")
    except Exception as e:
        print(f"⚠️ Could not auto-detect Unity version: {e}. Using fallback.")

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
            home / "Library/Application Support/com.wizards.mtga", # User Library
            Path("/Library/Application Support/com.wizards.mtga"),   # System-wide Library
            home / "Applications/MTGA.app",
            Path("/Applications/Epic Games/MagicTheGathering/MTGA.app")
        ]
    else:
        print(f"Unsupported OS: {system}. Please manually locate the MTGA path.")
        return None

    print("🔍 Searching for MTG Arena installation...")
    for path in paths_to_check:
        if path.exists():
            is_app_bundle = str(path).endswith(".app")
            data_root = path / "Contents/Resources/Data" if is_app_bundle and system == "Darwin" else path
            
            asset_bundle_path = data_root / "Downloads/AssetBundle"
            if asset_bundle_path.exists():
                print(f"✅ MTG Arena found at: {path}")
                return path

    print("❌ Could not automatically find MTG Arena installation.")
    return None

def get_original_card_details(card_name: str) -> Optional[Tuple[str, str]]:
    """Fetches the original set and collector number for a card by its name using the search endpoint."""
    try:
        search_query = f'!"{card_name}"'
        api_url = f"https://api.scryfall.com/cards/search?q={requests.utils.quote(search_query)}"
        response = requests.get(api_url)
        response.raise_for_status()
        time.sleep(0.1)
        data = response.json()
        if data.get("total_cards", 0) > 0:
            card_data = data["data"][0]
            return card_data.get('set', '').upper(), card_data.get('collector_number', '')
        else:
            print(f"   - ❌ Scryfall search returned no results for '{card_name}'.")
            return None
    except requests.exceptions.RequestException:
        print(f"   - ❌ Could not find original card details for '{card_name}' on Scryfall.")
        return None

def get_card_data_from_url(url: str) -> Optional[Dict]:
    """
    Fetches card data from a Scryfall URL, automatically converting
    webpage URLs to API URLs if necessary.
    """
    api_url = url
    if "scryfall.com/card" in api_url:
        parts = api_url.split('/')
        if len(parts) > 6:
            api_url = '/'.join(parts[:-1])

    try:
        response = requests.get(api_url)
        response.raise_for_status()
        time.sleep(0.1)
        return response.json()
    except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
        print(f"❌ Error fetching card data for {url}: {e}")
        return None

def download_image(url: str, dest_path: Path) -> bool:
    """Downloads an image from a URL to a destination path."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error downloading image {url}: {e}")
        return False

def get_data_path(mtga_path: Path) -> Path:
    """Gets the correct MTGA_Data path for Windows or macOS."""
    if platform.system() == "Darwin" and str(mtga_path).endswith(".app"):
        return mtga_path / "Contents/Resources/Data"
    return mtga_path

def get_mtga_database(data_path: Path) -> Optional[Path]:
    """Finds the main SQLite database for MTG Arena."""
    db_subfolders_to_check = [
        data_path / "Downloads/Data",
        data_path / "Downloads/Raw"
    ]
    db_filename_patterns = [
        "data_cards_*.mtga",
        "Raw_CardDatabase_*.mtga"
    ]

    for db_folder in db_subfolders_to_check:
        if db_folder.exists():
            for pattern in db_filename_patterns:
                db_files = list(db_folder.glob(pattern))
                if db_files:
                    return max(db_files, key=os.path.getmtime)
    
    print("❌ Could not find MTG Arena card database file.")
    return None
    
def get_card_and_art_ids_from_db(db_path: Path, swaps: List[Dict]) -> Dict[str, Tuple[int, int]]:
    """
    Retrieves MTGA card IDs (GrpId) and Art IDs using ExpansionCode and CollectorNumber.
    """
    card_data = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n🔍 Finding Arena IDs for cards using Set and Collector Number...")
    for swap in swaps:
        source_name = swap.get("source_card_name")
        exp_code = swap.get("expansion_code")
        coll_num = swap.get("collector_number")

        if not all([source_name, exp_code, coll_num]):
            continue

        try:
            # Fetch both GrpId and ArtId
            query = "SELECT GrpId, ArtId FROM cards WHERE ExpansionCode = ? AND CollectorNumber = ?"
            cursor.execute(query, (exp_code, str(coll_num)))
            result = cursor.fetchone()
            if result:
                card_data[source_name] = (result[0], result[1]) # Store as a tuple (GrpId, ArtId)
        except sqlite3.Error as e:
            print(f"❌ Database error looking for {source_name}: {e}")
            continue
    
    conn.close()
    return card_data

def find_asset_bundles(data_path: Path, card_id: int, art_id: int) -> Tuple[Optional[Path], Optional[Path]]:
    """Finds the asset bundles containing a card's art and data."""
    asset_dir = data_path / "Downloads/AssetBundle"
    card_art_bundle, cards_bundle = None, None
    
    print(f"   - Searching for bundles for card ID: {card_id} and art ID: {art_id} in {asset_dir}")

    if not asset_dir.exists():
        print("   - ❌ AssetBundle directory does not exist!")
        return None, None

    # --- ART BUNDLE LOGIC: Handles individual files first, then ranged bundles ---
    art_bundle_files = list(asset_dir.glob(f"{art_id}_CardArt_*.mtga"))
    if art_bundle_files:
        card_art_bundle = art_bundle_files[0]
        print(f"     - ✅ Found matching art file: {card_art_bundle.name}")
    else:
        art_bundles_ranged = list(asset_dir.glob("cardart_*.bundle"))
        for bundle in art_bundles_ranged:
            try:
                parts = bundle.stem.split('_')
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    start_id, end_id = int(parts[1]), int(parts[2])
                    if start_id <= art_id <= end_id:
                        card_art_bundle = bundle
                        print(f"     - ✅ Found matching ranged art bundle: {bundle.name}")
                        break
            except (ValueError, IndexError):
                continue

    # --- CARDS BUNDLE LOGIC: Handles individual files first, then ranged bundles ---
    cards_bundle_files = list(asset_dir.glob(f"{card_id}_Card_*.mtga"))
    if cards_bundle_files:
        cards_bundle = cards_bundle_files[0]
        print(f"     - ✅ Found matching card data file: {cards_bundle.name}")
    else:
        cards_bundles_ranged = list(asset_dir.glob("cards_*.bundle"))
        for bundle in cards_bundles_ranged:
            try:
                parts = bundle.stem.split('_')
                if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                    start_id, end_id = int(parts[1]), int(parts[2])
                    if start_id <= card_id <= end_id:
                        cards_bundle = bundle
                        print(f"     - ✅ Found matching ranged cards bundle: {bundle.name}")
                        break
            except (ValueError, IndexError):
                continue
    
    # --- FINAL FALLBACK ---
    # If we found an art bundle but not a cards bundle, assume they are the same file.
    if card_art_bundle and not cards_bundle:
        print("     - ⚠️ Could not find a separate cards bundle. Assuming data is in the art bundle.")
        cards_bundle = card_art_bundle
            
    return card_art_bundle, cards_bundle

# --- Core Logic Functions ---

def generate_swap_file(source_set: str, target_set: str):
    """Generates a swaps.json file by matching cards from a source set to a target set based on their original printed name."""
    print(f"\n--- Generating swap file from {source_set.upper()} to {target_set.upper()} ---")
    
    # 1. Fetch all cards from the target set and create a mapping
    print(f"Fetching card data from target set: {target_set.upper()}...")
    target_matches = {}
    next_page_url = f"https://api.scryfall.com/cards/search?q=set:{target_set}"
    while next_page_url:
        try:
            response = requests.get(next_page_url)
            response.raise_for_status()
            data = response.json()
            for card in data.get('data', []):
                base_name = card.get('printed_name') or card.get('name')
                if base_name:
                    target_matches[base_name] = card.get('uri')
            next_page_url = data.get('next_page')
            time.sleep(0.1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching data from Scryfall for target set: {e}")
            return
            
    print(f"Found {len(target_matches)} unique base cards in {target_set.upper()}.")


    print(f"Fetching card data from source set: {source_set.upper()}...")
    source_matches = {}
    next_page_url = f"https://api.scryfall.com/cards/search?q=set:{source_set}"
    while next_page_url:
        try:
            response = requests.get(next_page_url)
            response.raise_for_status()
            data = response.json()
            for card in data.get('data', []):
                base_name = card.get('printed_name') or card.get('name')
                if base_name:
                    source_matches[base_name] = card.get('uri')
            next_page_url = data.get('next_page')
            time.sleep(0.1)
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching data from Scryfall for target set: {e}")
            return
            
    print(f"Found {len(source_matches)} unique base cards source in {source_set.upper()}.")


    # first print the first card of each set to verify
    if source_matches:
        first_source_card = next(iter(source_matches))
        print(f"First card in source set ({source_set.upper()}): {first_source_card} - {source_matches[first_source_card]}")
    if target_matches:
        first_target_card = next(iter(target_matches))
        print(f"First card in target set ({target_set.upper()}): {first_target_card} - {target_matches[first_target_card]}")


    swaps_to_generate = []


    # for each card in the source set, check if its base name exists in the target set
    for base_name in source_matches:
        # we call the url found. This has a json with printed_name as its source name, but 'printed_name' is the *original* name from the target set.

        request_url = source_matches[base_name]
        card_data = requests.get(request_url).json()
        # log card data 
        if card_data:
            printed_name = card_data.get('name')
            print(f"Source card '{base_name}' has printed name '{printed_name}'")

            original_coll_num = card_data.get('collector_number', '')

            swaps_to_generate.append({
                        "source_card_name": printed_name,
                        "expansion_code": source_set.upper(),
                        "collector_number": original_coll_num,
                        "target_api_url": target_matches.get(printed_name)
                    })
        else:
            print(f"❌ No card data found for source card '{base_name}'.")


    if not swaps_to_generate:
        print(f"\nℹ️ No valid matches found between {source_set.upper()} and {target_set.upper()}.")
        return

    swaps_to_generate.sort(key=lambda x: x['source_card_name'])
    try:
        with open("swaps.json", "w") as f:
            json.dump(swaps_to_generate, f, indent=4)
        print(f"\n✅ Successfully generated `swaps.json` with {len(swaps_to_generate)} entries.")
    except IOError as e:
        print(f"❌ Error writing to `swaps.json`: {e}")


def perform_swap(mtga_path: Optional[Path]):
    """Main function to perform all card swaps defined in swaps.json."""
    if not mtga_path:
        print("\n❌ MTG Arena path not set. Please find or select it first.")
        return
    
    print("\n--- Starting Card Swap Process ---")
    data_path = get_data_path(mtga_path)
    
    try:
        with open("swaps.json", "r") as f: swaps_config = json.load(f)
    except FileNotFoundError:
        print("❌ `swaps.json` not found! Please generate it first."); return
    except json.JSONDecodeError:
        print("❌ `swaps.json` is not valid JSON. Please check its syntax."); return

    db_path = get_mtga_database(data_path)
    if not db_path: return
        
    card_data_map = get_card_and_art_ids_from_db(db_path, swaps_config)
    
    found_count = len(card_data_map)
    total_count = len(swaps_config)
    print(f"\nFound {found_count} out of {total_count} cards in the database.")
    
    if found_count < total_count:
        source_names_in_config = {swap['source_card_name'] for swap in swaps_config}
        missing_cards = source_names_in_config - set(card_data_map.keys())
        if missing_cards: print(f"⚠️ Could not find in database: {', '.join(sorted(list(missing_cards)))}")

    if not card_data_map:
        print("\nNo cards to process. Exiting swap.")
        return

    temp_dir = Path("./temp_art")
    backup_dir = Path("./MTGA_Swapper_Backups")
    temp_dir.mkdir(exist_ok=True); backup_dir.mkdir(exist_ok=True)
    
    print("\nProcessing swaps...")
    try:
        for swap in swaps_config:
            source_name = swap['source_card_name']
            if source_name not in card_data_map: continue
                
            card_id, art_id = card_data_map[source_name]
            print(f"\nProcessing swap for '{source_name}' (ID: {card_id})")

            target_url = swap.get('target_api_url') or swap.get('target_scryfall_url')
            if not target_url:
                print(f"   Skipping '{source_name}' because its target URL is missing in swaps.json.")
                continue

            target_data = get_card_data_from_url(target_url)
            if not target_data: print(f"   Skipping '{source_name}' due to API error."); continue
                
            target_name = target_data.get('name', source_name)
            
            image_uris = target_data.get('image_uris', {})
            image_url = None

            image_url = image_uris.get('art_crop')

            if not image_url: 
                print(f"   Could not find art for '{target_name}'. Skipping."); continue
            
            image_path = temp_dir / f"{card_id}.jpg"
            if not download_image(image_url, image_path): print(f"   Failed to download art for '{target_name}'. Skipping."); continue

            art_bundle_path, cards_bundle_path = find_asset_bundles(data_path, card_id, art_id)
            if not all([art_bundle_path, cards_bundle_path]): print(f"   ❌ Could not locate asset bundles for '{source_name}'. Skipping."); continue

            for bundle_path in [art_bundle_path, cards_bundle_path]:
                if bundle_path:
                    backup_path = backup_dir / bundle_path.name
                    if not backup_path.exists():
                        shutil.copy(bundle_path, backup_dir)
                        print(f"      - Backed up {bundle_path.name}")
                    else:
                        print(f"      - Backup for {bundle_path.name} already exists. Skipping.")
            
            env_art = UnityPy.load(str(art_bundle_path))
            
            all_textures = [obj.read() for obj in env_art.objects if obj.type.name == "Texture2D"]
            
            textures_with_image = [tex for tex in all_textures if hasattr(tex, 'image') and tex.image]

            if textures_with_image:
                textures_with_image.sort(key=lambda x: x.image.width * x.image.height, reverse=True)
                main_art_texture = textures_with_image[0]
                main_art_texture.image = Image.open(image_path)
                main_art_texture.save()
                
                with open(art_bundle_path, "wb") as f:
                    f.write(env_art.file.save())
                print(f"   -> Art replaced in: {art_bundle_path.name}")
            else:
                print(f"   -> ❌ No textures found in {art_bundle_path.name}")

            if cards_bundle_path != art_bundle_path:
                env_cards = UnityPy.load(str(cards_bundle_path))
            else:
                env_cards = env_art

            for obj in env_cards.objects:
                if obj.type.name == "TextAsset":
                    data = obj.read()
                    if data.m_Name == f"Card_Title_{card_id}":
                        data.text = target_name
                        data.save()
                        with open(cards_bundle_path, "wb") as f:
                            f.write(env_cards.file.save())
                        print(f"   -> Name replaced in: {cards_bundle_path.name}")
                        break
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        print("\n--- ✅ Swap Process Complete! ---")
        print("Launch MTG Arena to see your changes.")

def restore_backups(mtga_path: Optional[Path]):
    """Restores original asset bundles from the backup directory."""
    if not mtga_path:
        print("\n❌ MTG Arena path not set. Please find or select it first.")
        return
        
    print("\n--- Restoring Original Game Files ---")
    data_path = get_data_path(mtga_path)
    
    asset_dir = data_path / "Downloads/AssetBundle"
    backup_dir = Path("./MTGA_Swapper_Backups")
    
    if not backup_dir.exists() or not any(backup_dir.iterdir()):
        print("ℹ️ No backups found. Nothing to restore."); return
        
    backups = list(backup_dir.glob("*.bundle")) + list(backup_dir.glob("*.mtga"))
    print(f"Found {len(backups)} files to restore.")
    for backup_file in backups: shutil.copy(backup_file, asset_dir / backup_file.name)

    print("\n--- ✅ Restore Complete! ---")
    print("Your game files have been returned to their original state.")

# --- GUI Application using Tkinter ---

class StdoutRedirector:
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
        self.geometry("650x600")
        self.resizable(False, False)
        self.mtga_path: Optional[Path] = None
        self.create_widgets()
        sys.stdout = StdoutRedirector(self.log_widget)
        sys.stderr = StdoutRedirector(self.log_widget)
        
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        title_font = font.Font(family="Helvetica", size=20, weight="bold")
        subtitle_font = font.Font(family="Helvetica", size=11)
        ttk.Label(main_frame, text="MTG Arena Set Swapper", font=title_font).pack(pady=(0, 5))
        ttk.Label(main_frame, text="A tool to replace digital-only card art and names.", font=subtitle_font).pack(pady=(0, 10))
        path_frame = ttk.LabelFrame(main_frame, text="MTG Arena Path", padding="10")
        path_frame.pack(fill="x", pady=10)
        self.path_var = tk.StringVar(); self.path_var.set("Path: Not Found")
        ttk.Label(path_frame, textvariable=self.path_var, wraplength=400).pack(side="left", fill="x", expand=True)
        path_buttons_frame = ttk.Frame(path_frame); path_buttons_frame.pack(side="right")
        self.find_auto_button = ttk.Button(path_buttons_frame, text="Find Auto", command=self.find_path_auto)
        self.find_auto_button.pack(side="left", padx=(0, 5))
        self.find_manual_button = ttk.Button(path_buttons_frame, text="Select Manual", command=self.find_path_manual)
        self.find_manual_button.pack(side="left")
        log_frame = ttk.Frame(main_frame); log_frame.pack(fill="both", expand=True, pady=5)
        self.log_widget = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', bg="black", fg="white", font=("Courier New", 10))
        self.log_widget.pack(fill="both", expand=True)
        controls_frame = ttk.Frame(main_frame); controls_frame.pack(fill="x", pady=10)
        gen_frame = ttk.Frame(controls_frame); gen_frame.pack(fill="x", pady=5)
        
        ttk.Label(gen_frame, text="Source Set:").pack(side="left", padx=(0, 5))
        self.source_set_entry = ttk.Entry(gen_frame, width=10); self.source_set_entry.insert(0, "om1"); self.source_set_entry.pack(side="left", padx=5)
        ttk.Label(gen_frame, text="Target Set:").pack(side="left", padx=(0, 5))
        self.target_set_entry = ttk.Entry(gen_frame, width=10); self.target_set_entry.insert(0, "spm"); self.target_set_entry.pack(side="left", padx=5)
        self.generate_button = ttk.Button(gen_frame, text="Generate swaps.json", command=lambda: self.run_in_thread(generate_swap_file, self.source_set_entry.get(), self.target_set_entry.get()))
        self.generate_button.pack(side="left", padx=5)
        
        action_frame = ttk.Frame(main_frame); action_frame.pack(fill="x", pady=10)
        
        # Action Buttons
        self.swap_button = ttk.Button(action_frame, text="Apply Swaps", command=lambda: self.run_in_thread(perform_swap, self.mtga_path))
        self.swap_button.pack(side="left", expand=True, fill="x", padx=2)
        
        self.restore_button = ttk.Button(action_frame, text="Restore Originals", command=lambda: self.run_in_thread(restore_backups, self.mtga_path))
        self.restore_button.pack(side="left", expand=True, fill="x", padx=2)
        
        self.exit_button = ttk.Button(action_frame, text="Exit", command=self.destroy)
        self.exit_button.pack(side="left", expand=True, fill="x", padx=2)

    def find_path_auto(self):
        self.run_in_thread(self._find_path_auto_task)
            
    def _find_path_auto_task(self):
        self.mtga_path = find_mtga_path()
        self.path_var.set(f"Path: {self.mtga_path}" if self.mtga_path else "Path: Not Found")
        if self.mtga_path:
            # Configure Unity version immediately after finding the path
            self.after(0, lambda: configure_unity_version(get_data_path(self.mtga_path)))

    def find_path_manual(self):
        initial_dir = {"Windows": "C:/", "Darwin": "/Applications"}.get(platform.system(), "/")
        path = filedialog.askdirectory(initialdir=initial_dir, title="Select MTG Arena Folder")
        if path:
            selected_path = Path(path)
            data_path = get_data_path(selected_path)
            asset_bundle_path = data_path / "Downloads/AssetBundle"
            if asset_bundle_path.exists():
                self.mtga_path = selected_path
                self.path_var.set(f"Path: {self.mtga_path}")
                print(f"✅ Manually selected path is valid: {self.mtga_path}")
                # Configure Unity version once path is found
                configure_unity_version(data_path)
            else:
                self.mtga_path = None
                self.path_var.set("Path: Invalid Folder Selected")
                print(f"❌ Manually selected path is NOT a valid MTGA folder: {selected_path}")
                messagebox.showerror("Invalid Folder", "The selected folder is not a valid MTG Arena installation.")

    def run_in_thread(self, target_func, *args):
        self.set_buttons_state('disabled')
        thread = threading.Thread(target=target_func, args=args, daemon=True)
        thread.start()
        self.monitor_thread(thread)

    def monitor_thread(self, thread):
        if thread.is_alive():
            self.after(100, lambda: self.monitor_thread(thread))
        else:
            self.set_buttons_state('normal')

    def set_buttons_state(self, state):
        buttons = [
            self.generate_button, self.swap_button, 
            self.restore_button, self.exit_button, self.find_auto_button, 
            self.find_manual_button
        ]
        
        for button in buttons:
            if hasattr(button, 'config'):
                button.config(state=state)

if __name__ == "__main__":
    app = App()
    app.mainloop()

