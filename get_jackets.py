import pandas as pd
import requests
import os
import time
import re
from PIL import Image
import io

# --- Configuration ---
CSV_NAMES_FILE = 'names.csv'
DOWNLOAD_DIR = 'jackets'
MISSING_LOG = 'missing_jackets.txt'
API_URL = "https://arcaea.fandom.com/api.php"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Functions ---

def is_square(file_path):
    """Returns True if the image exists and width == height."""
    if not os.path.exists(file_path):
        return False
    try:
        with Image.open(file_path) as img:
            w, h = img.size
            return w == h and w > 0
    except:
        return False

def get_image_metadata(file_title):
    """Gets the URL and dimensions from the Wiki API."""
    params = {
        "action": "query",
        "format": "json",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url|size"
    }
    try:
        res = requests.get(API_URL, params=params).json()
        pages = res['query']['pages']
        for p in pages:
            if 'imageinfo' in pages[p]:
                info = pages[p]['imageinfo'][0]
                return info['url'], info['width'], info['height']
    except:
        return None, 0, 0
    return None, 0, 0

def search_wiki_for_square(song_title):
    """Searches for files and picks the first square one it finds."""
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": f"intitle:{song_title}",
        "srnamespace": 6,
        "srlimit": 5
    }
    
    try:
        res = requests.get(API_URL, params=params).json()
        search_results = res.get('query', {}).get('search', [])
        
        for result in search_results:
            title = result['title']
            url, w, h = get_image_metadata(title)
            # Accept any square image found on the Wiki
            if w == h and w > 100: # Ignore tiny icons
                return url
        return None
    except:
        return None

# --- Main Process ---

try:
    df = pd.read_csv(CSV_NAMES_FILE, header=None)
    all_songs = df[0].unique()
    print(f"📄 Loaded {len(all_songs)} songs.")
except Exception as e:
    print(f"❌ Error: {e}")
    exit()

success_count = 0
skipped_count = 0
missing_songs = []

print("🚀 Scanning for missing or non-square jackets...")

for song in all_songs:
    song_clean = str(song).strip()
    safe_name = re.sub(r'[\\/*?:"<>|]', "", song_clean)
    save_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.jpg")

    # If it's already square, we don't touch it.
    if is_square(save_path):
        skipped_count += 1
        continue

    print(f"Searching for: {song_clean}...", end=" ", flush=True)
    
    best_url = search_wiki_for_square(song_clean)
    
    if best_url:
        try:
            img_data = requests.get(best_url).content
            with Image.open(io.BytesIO(img_data)) as img:
                w, h = img.size
                if w == h:
                    with open(save_path, 'wb') as f:
                        f.write(img_data)
                    print(f"✅ Downloaded ({w}x{h})")
                    success_count += 1
                else:
                    print(f"❌ Wiki result was {w}x{h} (not square).")
                    missing_songs.append(song_clean)
            time.sleep(0.3)
        except:
            print("❌ Download failed.")
            missing_songs.append(song_clean)
    else:
        print("❓ No square match found.")
        missing_songs.append(song_clean)

# 4. Save results
with open(MISSING_LOG, 'w', encoding='utf-8') as f:
    for s in missing_songs:
        f.write(s + "\n")

print(f"\nDone! Downloaded {success_count} new jackets.")
print(f"Already had {skipped_count} square jackets.")
print(f"Still missing {len(missing_songs)} jackets (logged in {MISSING_LOG}).")