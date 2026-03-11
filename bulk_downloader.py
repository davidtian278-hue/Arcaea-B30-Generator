import requests
import os
from PIL import Image
import io
import re
import sys
from bs4 import BeautifulSoup

# --- Configuration ---
DOWNLOAD_DIR = 'jackets'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_direct_from_wiki(page_url):
    """Finds the actual image source from a Fandom page."""
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        if res.status_code != 200: return None
        soup = BeautifulSoup(res.text, 'html.parser')
        
        full_res = soup.find('a', class_='fullImageLink')
        if full_res and full_res.find('a'):
            return full_res.find('a')['href']
            
        img_tag = soup.find('img', class_='pi-image-thumbnail') or soup.find('img', class_='thumbimage')
        if img_tag:
            return img_tag['src'].split('/revision')[0]
    except:
        return None
    return None

def process_downloads():
    print("📥 Smart Bulk Downloader (with Custom Naming)")
    print("-" * 50)
    print("Format options:")
    print("1. Just the URL")
    print("2. URL followed by the Song Name on the next line")
    print("Type 'DONE' to start.")
    print("-" * 50)

    input_lines = []
    while True:
        line = sys.stdin.readline().strip()
        if line.upper() == "DONE": break
        if line: input_lines.append(line)

    # Group lines into (URL, Optional Name) pairs
    pairs = []
    i = 0
    while i < len(input_lines):
        item = input_lines[i]
        # Check if this line is a URL
        if item.startswith("http"):
            # Check if the NEXT line is NOT a URL (meaning it's a name)
            if i + 1 < len(input_lines) and not input_lines[i+1].startswith("http"):
                pairs.append((item, input_lines[i+1]))
                i += 2
            else:
                pairs.append((item, None))
                i += 1
        else:
            i += 1 # Skip stray text that isn't a URL

    success = 0
    fail = 0

    for url, custom_name in pairs:
        download_url = url
        
        # Handle Wiki pages
        if "fandom.com/wiki/" in url and not url.lower().endswith(('.jpg', '.png', '.jpeg')):
            print(f"🔍 Searching page for image...")
            found_url = get_direct_from_wiki(url)
            if found_url:
                download_url = found_url
                if download_url.startswith("//"): download_url = "https:" + download_url

        try:
            res = requests.get(download_url, headers=HEADERS, timeout=15)
            img = Image.open(io.BytesIO(res.content))
            w, h = img.size
            
            # Square Check
            if w != h:
                print(f"⏭️  Skipped: Not square ({w}x{h})")
                fail += 1
                continue

            # Determine Filename
            if custom_name:
                filename = custom_name
            else:
                # Try to guess from URL
                name_part = re.search(r'(?:File:|/)([^/]+)\.(?:jpg|png|jpeg)', url, re.I)
                filename = name_part.group(1).replace("_", " ") if name_part else f"manual_{success}"
            
            # Clean filename for Windows
            filename = re.sub(r'[\\/*?:"<>|]', "", filename) + ".jpg"
            
            # Save
            if img.mode != "RGB": img = img.convert("RGB")
            img.save(os.path.join(DOWNLOAD_DIR, filename), "JPEG", quality=95)
            
            print(f"✅ Saved: {filename} ({w}x{h})")
            success += 1

        except Exception as e:
            print(f"❌ Error with {url[-20:]}: {e}")
            fail += 1

    print("-" * 50)
    print(f"Done! Success: {success} | Failed: {fail}")

if __name__ == "__main__":
    process_downloads()