import pandas as pd
import requests
import os
import time
import re

# --- Configuration ---
CSV_NAMES_FILE = 'names.csv'
DOWNLOAD_DIR = 'jackets'
MISSING_LOG = 'missing_jackets.txt'
API_URL = "https://arcaea.fandom.com/api.php"

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# --- Functions ---

def search_wiki_for_file(song_title):
    """Searches the wiki for a file matching the song title."""
    # We search the 'File' namespace (6) for the song title
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": f"intitle:{song_title}",
        "srnamespace": 6, # File namespace
        "srlimit": 3      # Look at the top 3 results
    }
    
    try:
        res = requests.get(API_URL, params=params).json()
        search_results = res.get('query', {}).get('search', [])
        
        if not search_results:
            # Try a broader search without 'intitle' if that failed
            params["srsearch"] = song_title
            res = requests.get(API_URL, params=params).json()
            search_results = res.get('query', {}).get('search', [])

        # Look for the best match among results
        for result in search_results:
            title = result['title']
            # We want files that look like jackets (jpg or png)
            if title.lower().endswith(('.jpg', '.png', '.jpeg')):
                # Prefer files that actually contain the song name in the title
                return title
                
        return None
    except Exception as e:
        print(f"Search Error for {song_title}: {e}")
        return None

def get_direct_url(file_title):
    """Gets the actual download link for a specific Wiki File title."""
    params = {
        "action": "query",
        "format": "json",
        "titles": file_title,
        "prop": "imageinfo",
        "iiprop": "url"
    }
    try:
        res = requests.get(API_URL, params=params).json()
        pages = res['query']['pages']
        for p in pages:
            if 'imageinfo' in pages[p]:
                return pages[p]['imageinfo'][0]['url']
    except:
        return None
    return None

# --- Main Process ---

try:
    # Read names.csv (assuming one column of names)
    df = pd.read_csv(CSV_NAMES_FILE, header=None)
    all_songs = df[0].unique()
    print(f"📄 Loaded {len(all_songs)} unique songs from {CSV_NAMES_FILE}.")
except Exception as e:
    print(f"❌ Error reading {CSV_NAMES_FILE}: {e}")
    exit()

success_count = 0
missing_songs = []

print("🚀 Starting Smart Search and Download...")

for song in all_songs:
    song_clean = str(song).strip()
    
    # Windows-safe filename for your folder
    safe_name = re.sub(r'[\\/*?:"<>|]', "", song_clean)
    save_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.jpg")

    if os.path.exists(save_path):
        continue

    print(f"Searching: {song_clean}...", end=" ", flush=True)
    
    # 1. Search for a matching file title
    wiki_file_title = search_wiki_for_file(song_clean)
    
    if wiki_file_title:
        # 2. Get the actual URL
        direct_url = get_direct_url(wiki_file_title)
        
        if direct_url:
            try:
                img_data = requests.get(direct_url).content
                with open(save_path, 'wb') as f:
                    f.write(img_data)
                print(f"✅ Found as '{wiki_file_title}'")
                success_count += 1
                time.sleep(0.3) 
            except:
                print("❌ Download Error")
                missing_songs.append(song_clean)
        else:
            print("❌ URL Error")
            missing_songs.append(song_clean)
    else:
        print("❓ Not found")
        missing_songs.append(song_clean)

# 3. Save results
with open(MISSING_LOG, 'w', encoding='utf-8') as f:
    for s in missing_songs:
        f.write(s + "\n")

print(f"\nSummary: Downloaded {success_count} | Missing {len(missing_songs)}")
print(f"Check {MISSING_LOG} for any that were still missed.")