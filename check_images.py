import os
from PIL import Image

# --- Configuration ---
JACKET_DIR = 'jackets'
TARGET_SIZE = (768, 768)
LOG_FILE = 'wrong_sizes.txt'

def check_jackets():
    if not os.path.exists(JACKET_DIR):
        print(f"❌ Folder '{JACKET_DIR}' not found.")
        return

    wrong_files = []
    total_checked = 0

    print(f"🔍 Scanning '{JACKET_DIR}' for images that are not {TARGET_SIZE[0]}x{TARGET_SIZE[1]}...")

    # Loop through every file in the jackets folder
    for filename in os.listdir(JACKET_DIR):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            total_checked += 1
            path = os.path.join(JACKET_DIR, filename)
            
            try:
                with Image.open(path) as img:
                    width, height = img.size
                    if (width, height) != TARGET_SIZE:
                        wrong_files.append(f"{filename} ({width}x{height})")
            except Exception as e:
                print(f"⚠️ Could not read {filename}: {e}")

    # Output the results
    print("-" * 30)
    print(f"Total images checked: {total_checked}")
    print(f"Incorrect sizes found: {len(wrong_files)}")

    if wrong_files:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            for item in wrong_files:
                f.write(item + "\n")
        print(f"📄 List of wrong images saved to: {LOG_FILE}")
        
        # Optional: Ask user if they want to delete them
        confirm = input("Do you want to DELETE these incorrect images now? (y/n): ")
        if confirm.lower() == 'y':
            for item in wrong_files:
                # Extract filename from the string "filename.jpg (widthxheight)"
                fname = item.split(' (')[0]
                os.remove(os.path.join(JACKET_DIR, fname))
            print(f"🗑️ Deleted {len(wrong_files)} images.")
    else:
        print("✅ All images are the correct size!")

if __name__ == "__main__":
    check_jackets()