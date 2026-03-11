import discord
from discord.ext import commands
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2 import service_account
import io
import re
import asyncio

# --- CONFIG ---
DISCORD_TOKEN = 'MTQ4MDk5NjMxMDI1NjQ1MTcxNg.GPRHI2.9PjkSpqoQYQ8YW3g940I1DIgiuJedlOdKUkz_w'
GEMINI_API_KEY = 'AIzaSyA4GRZkGIG-uKArfF0xHA43pj4dkIgt7j4'
SERVICE_ACCOUNT_FILE = 'credentials.json'
SPREADSHEET_ID = '1k_ZbwO0Q9TCNKvvkOmRpwMUsH1XjygSDleEQakNfW0M'
SHEET_NAME = "Score Input" # The exact name of your tab
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# --- INITIALIZATION ---
genai.configure(api_key=GEMINI_API_KEY)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

VALID_MODELS = []
processed_messages = set() 

# --- 2. LOGIC HELPERS ---

def map_difficulty(text):
    """Maps based on your specific color rules: FTR=Purple, ETR=Light Purple, BYD=Red."""
    t = str(text).upper().strip()
    if any(x in t for x in ["FTR", "FUTURE", "PURPLE", "VIOLET"]): return "FTR"
    if any(x in t for x in ["ETR", "ETERNAL", "LIGHT PURPLE", "LAVENDER", "WHITE"]): return "ETR"
    if any(x in t for x in ["BYD", "BEYOND", "RED", "ORANGE", "CRIMSON"]): return "BYD"
    if any(x in t for x in ["PRS", "PRESENT", "GREEN"]): return "PRS"
    if any(x in t for x in ["PST", "PAST", "BLUE"]): return "PST"
    return "FTR"

def update_score_in_sheet(song_target, diff_target, score_value):
    try:
        if any(f in song_target.lower() for f in ["track", "complete", "new", "record", "clear"]):
            return "SKIP"

        service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES))
        
        # Standardize for comparison
        ai_song = song_target.strip().lower()
        final_diff = map_difficulty(diff_target)
        
        range_name = f"'{SHEET_NAME}'!A1:D2500"
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])
        if not rows: return "❌ Sheet Error: No data found."

        # --- STEP 1: STRICT EXACT MATCH ---
        row_index = -1
        for i, row in enumerate(rows):
            for cell in row[:3]:
                sheet_song = str(cell).strip().lower()
                if sheet_song == ai_song: # Exact Match check
                    if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                        row_index = i + 1
                        break
            if row_index != -1: break

        # --- STEP 2: FUZZY FALLBACK (Only if exact match fails) ---
        if row_index == -1:
            for i, row in enumerate(rows):
                for cell in row[:3]:
                    sheet_song = str(cell).strip().lower()
                    if not sheet_song: continue
                    # Only match if sheet name is a significant part of AI name
                    if sheet_song in ai_song or ai_song in sheet_song:
                        if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                            row_index = i + 1
                            break
                if row_index != -1: break

        if row_index == -1:
            return f"❓ No match for **{song_target}** on **{final_diff}**."

        # Update Column H
        update_range = f"'{SHEET_NAME}'!H{row_index}"
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=update_range,
            valueInputOption="USER_ENTERED", body={'values': [[score_value]]}
        ).execute()
        
        pm_tag = " 🏆 **PURE MEMORY!**" if int(score_value) >= 10000000 else ""
        return f"✅ **{song_target}** [{final_diff}] → **{score_value}**{pm_tag}"
    except Exception as e:
        return f"❌ Sheet Error: {str(e)}"

# --- 3. BOT EVENTS ---

@bot.event
async def on_ready():
    global VALID_MODELS
    print(f"✅ Bot online")
    try:
        discovered = [m.name.replace('models/', '') for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        VALID_MODELS = sorted(discovered, reverse=True)
    except:
        VALID_MODELS = ['gemini-1.5-flash']

@bot.event
async def on_message(message):
    global processed_messages
    if message.author.bot or message.id in processed_messages: return

    if message.attachments:
        images = [a for a in message.attachments if any(a.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg'])]
        if not images: return

        processed_messages.add(message.id)
        status_msg = await message.channel.send("🔍 Analyzing result...")
        report = []

        for attachment in images:
            img_bytes = await attachment.read()
            found_success = False 
            
            for model_name in VALID_MODELS:
                if found_success: break 
                
                try:
                    model = genai.GenerativeModel(model_name)
                    prompt = """
                    Extract Arcaea result: Song Title | Difficulty | Score.
                    
                    DIFFICULTY RULES:
                    - PURPLE badge = FUTURE (FTR).
                    - LIGHT PURPLE/WHITE badge = ETERNAL (ETR).
                    - RED/ORANGE badge = BEYOND (BYD).
                    - GREEN badge = PRESENT (PRS).

                    SCORE RULES:
                    1. LOCATION: SLIGHTLY UPPER-MIDDLE of the screen.
                    2. TARGET: Largest number. ONLY OUTPUT NUMBERS GREATER THAN 9 MILLION
                    3. IGNORE: Right side and lower half (High Score, Best, +score, ALSO IGNORE "FULL RECALL", "TRACK LOST", "TRACK COMPLETE"

                    
                    Format: Title | Difficulty | Score
                    """
                    
                    response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_bytes}])
                    ai_text = response.text.replace("**", "").replace("'", "").replace(",", "").strip()
                    
                    if "|" in ai_text:
                        parts = [p.strip() for p in ai_text.split("|")]
                        if len(parts) >= 3:
                            res = update_score_in_sheet(parts[0], parts[1], parts[2])
                            if res != "SKIP":
                                report.append(res)
                                found_success = True 
                                break 
                except: continue

            if not found_success:
                report.append("❌ Image could not be read.")

        if report:
            await status_msg.edit(content="📊 **Update Summary:**\n" + "\n".join(report))
        else:
            await status_msg.delete()
            
        if len(processed_messages) > 100:
            processed_messages.clear()

bot.run(DISCORD_TOKEN)