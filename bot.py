import discord
from discord.ext import commands
from discord import app_commands
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import re
import asyncio
import logging
from collections import deque
from datetime import datetime
from dotenv import load_dotenv
import os
import difflib

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("arcaea-bot")

# --- 1. CONFIGURATION ---
load_dotenv(override=True) 

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_FILE = 'credentials.json'

# Tab Names (Configurable via .env)
INPUT_TAB_NAME = os.getenv('INPUT_TAB_NAME', '점수 입력 [Score Input]')
B30_TAB_NAME = os.getenv('B30_TAB_NAME', 'B30 컨설턴트 [Overview]')

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# --- INITIALIZATION ---
client = genai.Client(api_key=GEMINI_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        logger.info(f"Synced slash commands for {self.user}")

bot = MyBot()

# --- 2. B30 IMAGE DESIGN CONSTANTS ---
JACKET_SIZE = 140
MARGIN = 20
HEADER_SPACE = 160 
BOTTOM_TEXT_SPACE = 80
COLUMNS = 6
ROWS = 5
PLACEHOLDER_PATH = "placeholder.png"
JACKET_FOLDER = "jackets" 

DIFF_COLORS = {
    'FTR': (190, 80, 255),
    'BYD': (255, 60, 60),
    'ETR': (220, 150, 255),
    'PRS': (150, 255, 150),
    'PST': (150, 150, 255)
}

FONT_CANDIDATES = [
    "arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

# --- 3. SCANNER LOGIC STATE ---
VALID_MODELS = [
    'gemini-2.5-flash',
    'gemini-3.0-flash', 
    'gemini-1.5-flash',
    'gemini-1.5-pro'
]
processed_messages = deque(maxlen=500)  
SONG_CACHE = [] 

# --- 4. LOGIC HELPERS ---

FUZZY_MATCH_THRESHOLD = 0.72  

_sheets_service = None

def get_sheets_service():
    global _sheets_service
    if _sheets_service is None:
        creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        _sheets_service = build('sheets', 'v4', credentials=creds)
    return _sheets_service

def fetch_song_list():
    global SONG_CACHE
    try:
        service = get_sheets_service()
        range_name = f"'{INPUT_TAB_NAME}'!A1:A2500" 
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])
        
        temp_cache = []
        for row in rows:
            if row:
                raw_name = str(row[0]).strip()
                clean_name = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_name).strip()
                if clean_name and clean_name not in temp_cache:
                    temp_cache.append(clean_name)
                    
        SONG_CACHE = temp_cache
        logger.info(f"Loaded {len(SONG_CACHE)} clean songs into autocomplete cache.")
    except Exception as e:
        logger.exception("Failed to fetch songs for cache")

def map_difficulty(text):
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

        service = get_sheets_service()
        ai_song = song_target.strip().lower()
        final_diff = map_difficulty(diff_target)
        used_fuzzy_ratio = False  
        
        range_name = f"'{INPUT_TAB_NAME}'!A1:D2500"
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])
        if not rows: return "Sheet Error: No data found."

        matched_song_name = song_target 

        # --- STEP 1: STRICT EXACT MATCH ---
        row_index = -1
        for i, row in enumerate(rows):
            for cell in row[:3]:
                raw_sheet_song = str(cell).strip()
                sheet_song = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip().lower()
                
                if sheet_song == ai_song: 
                    if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                        row_index = i + 1
                        matched_song_name = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip()
                        break
            if row_index != -1: break

        # --- STEP 2: FUZZY FALLBACK ---
        if row_index == -1:
            for i, row in enumerate(rows):
                for cell in row[:3]:
                    raw_sheet_song = str(cell).strip()
                    sheet_song = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip().lower()
                    
                    if not sheet_song: continue
                    if sheet_song in ai_song or ai_song in sheet_song:
                        if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                            row_index = i + 1
                            matched_song_name = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip()
                            break
                if row_index != -1: break

        # --- STEP 3: TOKEN OVERLAP & SIMILARITY RATIO FALLBACK ---
        if row_index == -1:
            best_ratio = 0.0
            best_row_idx = -1
            best_matched_name = ""

            def get_words(text):
                return set(re.findall(r'\w+', text.lower()))

            ai_words = get_words(ai_song)

            for i, row in enumerate(rows):
                for cell in row[:3]:
                    raw_sheet_song = str(cell).strip()
                    sheet_song_clean = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip()
                    sheet_song = sheet_song_clean.lower()
                    
                    if not sheet_song: continue
                    if len(row) > 3 and map_difficulty(row[3]) != final_diff: continue

                    sheet_words = get_words(sheet_song)
                    if sheet_words and sheet_words.issubset(ai_words):
                        row_index = i + 1
                        matched_song_name = sheet_song_clean
                        break

                    ratio = difflib.SequenceMatcher(None, sheet_song, ai_song).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_row_idx = i + 1
                        best_matched_name = sheet_song_clean
                        
                if row_index != -1: break

            if row_index == -1 and best_ratio > FUZZY_MATCH_THRESHOLD:
                row_index = best_row_idx
                matched_song_name = best_matched_name
                used_fuzzy_ratio = True
                logger.info(f"Fuzzy-matched '{song_target}' -> '{matched_song_name}' (ratio={best_ratio:.2f})")

        if row_index == -1:
            return f"No match for **{song_target}** on **{final_diff}**."

        clean_score = str(score_value).replace(",", "").strip()

        # --- SAFEGUARD CHECK ---
        if not clean_score.isdigit() or not (0 <= int(clean_score) <= 11000000):
            return f"❌ Skipped **{matched_song_name}**: The score '{clean_score}' is invalid. It must be a number between 0 and 11,000,000."
        
        # Update Column H
        update_range = f"'{INPUT_TAB_NAME}'!H{row_index}"
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=update_range,
            valueInputOption="USER_ENTERED", body={'values': [[clean_score]]}
        ).execute()

        ptt_display = ""
        try:
            b30_result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=f"'{B30_TAB_NAME}'!B8:F37"
            ).execute()
            b30_rows = b30_result.get('values', [])
            for b30_row in b30_rows:
                if len(b30_row) >= 5:
                    b30_title = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', str(b30_row[2])).strip().lower()
                    if b30_title == matched_song_name.lower() or b30_title in matched_song_name.lower() or matched_song_name.lower() in b30_title:
                        try:
                            ptt_val = float(b30_row[4])
                            ptt_display = f" | PTT: **{ptt_val:.4f}**"
                        except (ValueError, TypeError):
                            pass
                        break
        except Exception:
            pass

        pm_tag = " **PURE MEMORY!**" if int(clean_score) >= 10000000 else ""
        fuzzy_note = " _(approximate title match — please verify)_" if used_fuzzy_ratio else ""
        return f"**{matched_song_name}** [{final_diff}] -> **{clean_score}**{ptt_display}{pm_tag}{fuzzy_note}"
    except Exception as e:
        logger.exception("Error updating score in sheet")
        return f"Sheet Error: {str(e)}"

# --- 5. SLASH COMMANDS ---

async def song_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    matches = [song for song in SONG_CACHE if current.lower() in song.lower()]
    return [app_commands.Choice(name=match, value=match) for match in matches[:25]]

@bot.tree.command(name="submit", description="Manually upload an Arcaea score to the spreadsheet")
@app_commands.describe(
    song="Search for the song name", 
    difficulty="Select the difficulty", 
    score="Type your score (e.g. 9982341)"
)
@app_commands.choices(difficulty=[
    app_commands.Choice(name="Future (FTR)", value="FTR"),
    app_commands.Choice(name="Eternal (ETR)", value="ETR"),
    app_commands.Choice(name="Beyond (BYD)", value="BYD"),
    app_commands.Choice(name="Present (PRS)", value="PRS"),
    app_commands.Choice(name="Past (PST)", value="PST"),
])
@app_commands.autocomplete(song=song_autocomplete)
async def manual_submit(interaction: discord.Interaction, song: str, difficulty: app_commands.Choice[str], score: str):
    await interaction.response.defer()
    
    clean_score = score.replace(",", "").strip()
    if not clean_score.isdigit():
        return await interaction.followup.send("Please enter a valid number for the score.")

    res = update_score_in_sheet(song, difficulty.value, clean_score)
    
    if res == "SKIP":
        await interaction.followup.send(f"Skipped updating **{song}**.")
    else:
        await interaction.followup.send(res)


@bot.tree.command(name="b30", description="Generate your Arcaea B30 and Potential Stats")
@app_commands.describe(
    username="The name you want displayed on the image",
    current_ptt="Your current in-game Potential (e.g. 12.50)"
)
async def b30_slash(interaction: discord.Interaction, current_ptt: float = None, username: str = None):
    display_name = username if username else interaction.user.display_name
    await interaction.response.defer() 
    
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=f"'{B30_TAB_NAME}'!B8:F37").execute()
        rows = result.get('values', [])

        if not rows:
            return await interaction.followup.send(f"No data found in the spreadsheet ({B30_TAB_NAME}!B8:F37).")

        df = pd.DataFrame(rows, columns=['Rank', 'Level', 'Title', 'Score', 'PTT'])
        df['PTT'] = pd.to_numeric(df['PTT'], errors='coerce').fillna(0)
        
        b30_sum = df['PTT'].head(30).sum()
        b30_avg = b30_sum / 30
        top_10_sum = df['PTT'].head(10).sum()
        hypo_max = (b30_sum + top_10_sum) / 40
        gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        font_title = load_font(16)
        font_score = load_font(18)
        font_ptt = load_font(20)
        font_header = load_font(42)
        font_stats = load_font(22)
        font_date = load_font(16)

        canvas_w = (JACKET_SIZE + MARGIN) * COLUMNS + MARGIN
        canvas_h = HEADER_SPACE + (JACKET_SIZE + BOTTOM_TEXT_SPACE + MARGIN) * ROWS + MARGIN
        canvas = Image.new('RGB', (canvas_w, canvas_h), color=(10, 10, 15))
        draw = ImageDraw.Draw(canvas)

        draw.text((MARGIN, 20), f"{display_name}'s Best 30", fill=(255, 255, 255), font=font_header)
        ptt_display = f"PTT: {current_ptt:.2f}" if current_ptt is not None else "PTT: --.--"
        stats_text = f"{ptt_display}  |  B30 Avg: {b30_avg:.4f}  |  Max: {hypo_max:.4f}"
        
        draw.text((MARGIN, 75), stats_text, fill=(255, 215, 0), font=font_stats)
        draw.text((MARGIN, 115), f"Generated on: {gen_date}", fill=(150, 150, 150), font=font_date)

        if os.path.exists(PLACEHOLDER_PATH):
            placeholder_img = Image.open(PLACEHOLDER_PATH).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
        else:
            placeholder_img = Image.new('RGB', (JACKET_SIZE, JACKET_SIZE), (40, 40, 50))

        for index, row in df.iterrows():
            if index >= 30: break
            col, row_idx = index % COLUMNS, index // COLUMNS
            x = MARGIN + col * (JACKET_SIZE + MARGIN)
            y = HEADER_SPACE + MARGIN + row_idx * (JACKET_SIZE + BOTTOM_TEXT_SPACE + MARGIN)

            raw_title = str(row['Title'])
            diff_match = re.search(r'\[(FTR|BYD|ETR|PRS|PST)\]', raw_title, re.IGNORECASE)
            difficulty = diff_match.group(1).upper() if diff_match else 'FTR'
            clean_title = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST)\]\s*$', '', raw_title).strip()

            jacket_file_name = clean_title.replace(":", "").replace("/", "").strip()
            jacket_path = os.path.join(JACKET_FOLDER, f"{jacket_file_name}.jpg")
            
            if os.path.exists(jacket_path):
                img = Image.open(jacket_path).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
                canvas.paste(img, (x, y))
            else:
                canvas.paste(placeholder_img, (x, y))

            title_text = clean_title
            max_w = JACKET_SIZE - 5 
            
            if draw.textlength(title_text, font=font_title) > max_w:
                while draw.textlength(title_text + "..", font=font_title) > max_w:
                    title_text = title_text[:-1]
                title_text = title_text + ".."
            
            draw.text((x, y + JACKET_SIZE + 5), title_text, fill=(200, 200, 200), font=font_title)

            draw.text((x, y + JACKET_SIZE + 25), f"{row['Score']}", fill="white", font=font_score)
            ptt_color = DIFF_COLORS.get(difficulty, (255, 255, 255))
            draw.text((x, y + JACKET_SIZE + 48), f"PTT: {row['PTT']:.4f}", fill=ptt_color, font=font_ptt)

        with io.BytesIO() as binary:
            canvas.save(binary, 'PNG')
            binary.seek(0)
            await interaction.followup.send(file=discord.File(fp=binary, filename=f'{display_name}_b30.png'))

    except Exception as e:
        logger.exception("Error generating B30 image")
        await interaction.followup.send(f"Error generating B30: {e}")


# --- 6. BOT EVENTS ---

@bot.event
async def on_message(message):
    global processed_messages
    if (message.author.bot and not message.webhook_id) or message.author == bot.user or message.id in processed_messages: return

    if message.attachments:
        images = [a for a in message.attachments if any(a.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg'])]
        if not images: return

        processed_messages.append(message.id)
        status_msg = await message.channel.send("Analyzing result...")
        report = []

        for attachment in images:
            img_bytes = await attachment.read()
            extracted_data = None 
            
            for model_name in VALID_MODELS:
                if extracted_data: break 
                
                try:
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
                    
                    # --- UPDATED API CALL FOR THE NEW SDK ---
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            prompt, 
                            types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
                        ]
                    )
                    
                    ai_text = response.text.replace("**", "").strip()
                    
                    if "|" in ai_text:
                        parts = [p.strip() for p in ai_text.split("|")]
                        if len(parts) >= 3:
                            raw_title = parts[0]
                            raw_diff = parts[1]
                            clean_score_only = parts[2].replace(",", "").replace("'", "").strip()
                            
                            extracted_data = [raw_title, raw_diff, clean_score_only]
                            break 
                except Exception as e:
                    logger.warning(f"Model '{model_name}' failed to read image: {e}")
                    continue

            if extracted_data:
                title, diff, ai_score = extracted_data[0], extracted_data[1], extracted_data[2]
                
                title = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', title).strip()
                
                await status_msg.edit(content=f"Uploading **{title}** to spreadsheet...")
                res = update_score_in_sheet(title, diff, ai_score)
                if res != "SKIP": 
                    report.append(res)
                    
            else:
                report.append("Image could not be read. (Models may be exhausted or rate-limited)")

        if report:
            await status_msg.edit(content="**Update Summary:**\n" + "\n".join(report))
        else:
            await status_msg.delete()

# --- RUN BOT ---
bot.run(DISCORD_TOKEN)