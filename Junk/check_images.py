import os
from PIL import Image

def find_bad_jackets(folder_path="jackets"):
    if not os.path.exists(folder_path):
        print(f"❌ Error: Could not find the folder '{folder_path}'.")
        print("Please make sure the folder exists in the same directory as this script.")
        return

    print(f"🔍 Scanning '{folder_path}' for bad images (non-square or transparent)...\n")
    bad_files = []

    for filename in os.listdir(folder_path):
        # Only check image files
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
            continue

        filepath = os.path.join(folder_path, filename)
        try:
            with Image.open(filepath) as img:
                width, height = img.size
                reasons = []

                # 1. Check if it's far from square (5% margin of error)
                aspect_ratio = width / height
                if aspect_ratio < 0.95 or aspect_ratio > 1.05:
                    reasons.append(f"Not square (Ratio: {aspect_ratio:.2f}, Size: {width}x{height})")

                # 2. Check for transparent pixels
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img_rgba = img.convert("RGBA")
                    # Index 3 is the Alpha (transparency) channel
                    alpha_min, alpha_max = img_rgba.getextrema()[3]
                    
                    if alpha_min < 255:
                        reasons.append("Contains transparent pixels")

                # If we found any issues, add it to the bad list
                if reasons:
                    bad_files.append(f"• {filename}: {', '.join(reasons)}")
                    
        except Exception as e:
            bad_files.append(f"• {filename}: ⚠️ Corrupted or unreadable file ({e})")

    # Output the final report
    if not bad_files:
        print("✅ All jackets passed! (Within 5% of square and fully opaque)")
    else:
        print(f"🚨 Found {len(bad_files)} Bad Jacket Images:\n")
        for item in bad_files:
            print(item)

if __name__ == "__main__":
    # Make sure you have a folder named 'jackets' in the same place as this script
    find_bad_jackets("jackets")