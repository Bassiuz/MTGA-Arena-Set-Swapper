# MTGA Set Swapper
# A tool to replace the art and names of MTG Arena cards.
# Final version with all bug fixes and features.

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
        # List of potential parent directories for the game
        drives = [Path(f"{drive}:/") for drive in "CD" if Path(f"{drive}:/").exists()]
        base_paths = [
            "Program Files/Wizards of the Coast/MTGA",
            "Program Files (x86)/Wizards of the Coast/MTGA",
            "Program Files (x86)/Steam/steamapps/common/MTGA",
            "Program Files/Epic Games/MagicTheGathering"
        ]
        paths_to_check = [drive / path for drive in drives for path in base_paths]
        paths_to_check.append(home / "AppData/Local/Wizards of the Coast/MTGA")

    elif system == "Darwin": # macOS
        paths_to_check = [
            Path("/Applications/MTGA.app"),
            home / "Library/Application Support/com.wizards.mtga",
            Path("/Library/Application Support/com.wizards.mtga"),
            home / "Applications/MTGA.app",
            Path("/Applications/Epic Games/MagicTheGathering/MTGA.app")
        ]
    else:
        print(f"Unsupported OS: {system}. Please manually locate the MTGA path.")
        return None

    print("🔍 Searching for MTG Arena installation...")
    for path in paths_to_check:
        if path.exists():
            # Use our new, smarter helper to find the actual data root
            data_root = get_data_path(path)

            asset_bundle_path = data_root / "Downloads/AssetBundle"
            if asset_bundle_path.exists():
                print(f"✅ MTG Arena found at: {path}")
                # We return the main installation folder, not the data subfolder
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
    system = platform.system()
    if system == "Darwin" and str(mtga_path).endswith(".app"):
        return mtga_path / "Contents/Resources/Data"

    # For Windows, specifically check if a nested MTGA_Data folder exists
    nested_data_path = mtga_path / "MTGA_Data"
    if system == "Windows" and nested_data_path.exists():
        print(f"   -> Found nested MTGA_Data folder at: {nested_data_path}")
        return nested_data_path

    # Fallback for other structures where Downloads is in the main folder
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

def fetch_scryfall_set_data(set_code: str) -> List[Dict]:
    """Fetches all card data for a given set from Scryfall."""
    all_cards = []
    next_page_url = f"https://api.scryfall.com/cards/search?q=set:{set_code}"
    print(f"Fetching card data for set: {set_code.upper()}...")
    while next_page_url:
        try:
            response = requests.get(next_page_url)
            response.raise_for_status()
            data = response.json()
            all_cards.extend(data.get('data', []))
            next_page_url = data.get('next_page')
            time.sleep(0.1)  # Be nice to the API
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching data from Scryfall for set {set_code.upper()}: {e}")
            return []
    return all_cards

def generate_swap_file(source_set_code: str, target_set_code: str):
    """
    Generates a swaps.json file by matching cards between a source and target set using their Oracle ID.
    This is robust for sets with different card names but the same function (e.g., Universes Beyond reskins).
    """
    print(f"\n--- Generating swap file from {source_set_code.upper()} to {target_set_code.upper()} ---")

    # 1. Fetch data for both sets
    source_cards = fetch_scryfall_set_data(source_set_code)
    target_cards = fetch_scryfall_set_data(target_set_code)

    if not source_cards or not target_cards:
        print("❌ Could not fetch card data for one or both sets. Aborting.")
        return

    # 2. Create maps from Oracle ID to card data for efficient matching
    source_map_by_oracle = {card['oracle_id']: card for card in source_cards if 'oracle_id' in card}
    target_map_by_oracle = {card['oracle_id']: card for card in target_cards if 'oracle_id' in card}

    print(f"\nFound {len(source_map_by_oracle)} functional cards in {source_set_code.upper()}.")
    print(f"Found {len(target_map_by_oracle)} functional cards in {target_set_code.upper()}.")

    # 3. Find common Oracle IDs and generate swap entries
    swaps_to_generate = []
    common_oracle_ids = set(source_map_by_oracle.keys()) & set(target_map_by_oracle.keys())
    print(f"\nFound {len(common_oracle_ids)} matching functional cards between sets.")

    for oracle_id in sorted(common_oracle_ids):
        source_card = source_map_by_oracle[oracle_id]
        target_card = target_map_by_oracle[oracle_id]

        source_name = source_card.get('name')
        target_name = target_card.get('name')

        print(f" - Processing match for '{source_name}' -> '{target_name}'")

        expansion_code = source_card.get('set', '').upper()
        collector_number = source_card.get('collector_number')
        target_api_url = target_card.get('uri')

        if not all([source_name, expansion_code, collector_number, target_api_url]):
             print(f"   - ⚠️ Missing critical data for '{source_name}'. Skipping.")
             continue

        swaps_to_generate.append({
            "source_card_name": source_name,
            "expansion_code": expansion_code,
            "collector_number": collector_number,
            "target_api_url": target_api_url
        })
        print(f"   - ✅ Created swap entry for {source_name} [{expansion_code}-{collector_number}]")

    if not swaps_to_generate:
        print(f"\nℹ️ No valid matches found between {source_set_code.upper()} and {target_set_code.upper()}.")
        return

    # --- MODIFIED PART ---
    # Save swaps.json to the user's Downloads folder for better permissions on macOS
    output_path = Path.home() / "Downloads" / "swaps.json"
    try:
        with open(output_path, "w") as f:
            json.dump(swaps_to_generate, f, indent=4)
        print(f"\n✅ Successfully generated `swaps.json` in your Downloads folder.")
    except IOError as e:
        print(f"❌ Error writing to `swaps.json` in Downloads folder: {e}")


def perform_swap(mtga_path: Optional[Path]):
    """Main function to perform all card swaps defined in swaps.json."""
    if not mtga_path:
        print("\n❌ MTG Arena path not set. Please find or select it first.")
        return

    print("\n--- Starting Card Swap Process ---")
    data_path = get_data_path(mtga_path)

    # --- MODIFIED PART ---
    # Look for swaps.json in the user's Downloads folder
    swaps_file_path = Path.home() / "Downloads" / "swaps.json"
    try:
        with open(swaps_file_path, "r") as f: swaps_config = json.load(f)
        print(f"   -> Found swaps.json in your Downloads folder.")
    except FileNotFoundError:
        print(f"❌ `swaps.json` not found in your Downloads folder! Please generate it first."); return
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
    backup_dir = Path.home() / "MTGA_Swapper_Backups" # Also move backups to a user folder
    temp_dir.mkdir(exist_ok=True); backup_dir.mkdir(exist_ok=True)

    print("\nProcessing swaps...")
    # (The rest of the function remains the same)
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

            target_type_line = target_data.get('type_line', '')
            image_uris = target_data.get('image_uris', {})
            image_url = None
            is_saga = "Saga" in target_type_line

            if is_saga:
                image_url = image_uris.get('png')
                print("   -> Saga detected. Using full card image to preserve chapters.")
            else:
                image_url = image_uris.get('art_crop')

            if not image_url: 
                print(f"   Could not find art for '{target_name}'. Skipping."); continue

            image_path = temp_dir / f"{card_id}.png"
            if not download_image(image_url, image_path): print(f"   Failed to download art for '{target_name}'. Skipping."); continue

            art_bundle_path, cards_bundle_path = find_asset_bundles(data_path, card_id, art_id)
            if not all([art_bundle_path, cards_bundle_path]): print(f"   ❌ Could not locate asset bundles for '{source_name}'. Skipping."); continue

            for bundle_path in {art_bundle_path, cards_bundle_path}:
                if bundle_path:
                    backup_path = backup_dir / bundle_path.name
                    if not backup_path.exists():
                        shutil.copy(bundle_path, backup_dir)
                        print(f"        - Backed up {bundle_path.name}")
                    else:
                        print(f"        - Backup for {bundle_path.name} already exists. Skipping.")

            env_art = UnityPy.load(str(art_bundle_path))

            all_textures = [obj for obj in env_art.objects if obj.type.name == "Texture2D"]

            if all_textures:
                all_textures.sort(key=lambda x: x.read().m_Width * x.read().m_Height if hasattr(x.read(), 'm_Width') else 0, reverse=True)
                main_art_texture_obj = all_textures[0]
                main_art_texture = main_art_texture_obj.read()

                img = Image.open(image_path)
                if is_saga:
                    print("      -> Resizing Saga art to fit horizontal frame...")
                    target_width, target_height = main_art_texture.m_Width, main_art_texture.m_Height

                    original_width, original_height = img.size
                    new_height = int(target_width * (original_height / original_width))

                    if new_height > target_height:
                        new_height = target_height
                        target_width = int(new_height * (original_height / original_height))

                    resized_img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)

                    final_img = Image.new("RGB", (main_art_texture.m_Width, main_art_texture.m_Height), (0, 0, 0))
                    paste_x = (main_art_texture.m_Width - target_width) // 2
                    paste_y = (main_art_texture.m_Height - new_height) // 2
                    final_img.paste(resized_img, (paste_x, paste_y))
                    img = final_img

                main_art_texture.image = img
                main_art_texture_obj.save(main_art_texture)

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
                        obj.save(data)
                        print(f"   -> Name replaced in: {cards_bundle_path.name}")
                        break

            with open(cards_bundle_path, "wb") as f:
                f.write(env_cards.file.save())

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
       ## self.geometry("650x600")
       ## self.resizable(False, False)
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
