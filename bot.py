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
import math
import mimetypes
import re
import asyncio
import logging
from collections import deque
from datetime import datetime
from dotenv import load_dotenv
import os
import difflib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("arcaea-bot")

# --- 1. CONFIGURATION ---
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'credentials.json')

# Tab Names (Configurable via .env)
INPUT_TAB_NAME = os.getenv('INPUT_TAB_NAME', '점수 입력 [Score Input]')
DASHBOARD_TAB_NAME = os.getenv('DASHBOARD_TAB_NAME', '대시보드 [Dashboard]')
DASHBOARD_B50_RANGE = f"'{DASHBOARD_TAB_NAME}'!B8:F57"

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# --- INITIALIZATION ---
client = genai.Client(api_key=GEMINI_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await asyncio.to_thread(fetch_song_list)
        await self.tree.sync()
        logger.info(f"Synced slash commands for {self.user}")

bot = MyBot()

# --- 2. B50 IMAGE DESIGN CONSTANTS ---
JACKET_SIZE = 140
MARGIN = 20
SIDE_PADDING = 50
HORIZONTAL_GAP = 40
VERTICAL_GAP = 20
HEADER_SPACE = 160 
BOTTOM_TEXT_SPACE = 80
COLUMNS = 5
ROWS = 10
BEST_SCORE_COUNT = 50
TOP_SCORE_COUNT = 10
DIFFICULTY_BADGE_SIDE = 40
DIFFICULTY_BADGE_RADIUS = round(DIFFICULTY_BADGE_SIDE / (2 ** 0.5))
BACKGROUND_TOP = (43, 18, 72)
BACKGROUND_BOTTOM = (5, 15, 45)
PLACEHOLDER_PATH = os.path.join(BASE_DIR, "placeholder.png")
JACKET_FOLDER = os.path.join(BASE_DIR, "jackets")

DIFF_COLORS = {
    'INS': (65, 75, 200),
    'FTR': (190, 80, 255),
    'BYD': (255, 60, 60),
    'ETR': (220, 150, 255),
    'PRS': (150, 255, 150),
    'PST': (150, 150, 255)
}

DIFFICULTY_JACKET_ALIASES = {
    ('pragmatism -resurrection-', 'BYD'): 'PRAGMATISM',
    ('ignotus afterburn', 'BYD'): 'Ignotus',
    ('red and blue and green', 'BYD'): 'Red and Blue',
    ('singularity vvvip', 'BYD'): 'Singularity',
    ('vicious [anti] heroism', 'BYD'): 'Vicious Heroism',
    ('axium divergence', 'BYD'): 'Axium Crisis',
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

def jacket_path_for_chart(title, difficulty):
    alias_title = DIFFICULTY_JACKET_ALIASES.get((title.casefold(), difficulty), title)
    candidate_titles = [
        f"{alias_title} [{difficulty}]",
        f"{title} [{difficulty}]",
        title,
        alias_title,
    ]
    checked_paths = set()
    for candidate_title in candidate_titles:
        safe_title = re.sub(r'[<>:"/\\|?*]', '', candidate_title).strip()
        candidate_path = os.path.join(JACKET_FOLDER, f"{safe_title}.jpg")
        if candidate_path not in checked_paths and os.path.exists(candidate_path):
            return candidate_path
        checked_paths.add(candidate_path)
    return None

def create_vertical_gradient(width, height, top_color, bottom_color):
    image = Image.new('RGB', (width, height), top_color)
    draw = ImageDraw.Draw(image)
    denominator = max(height - 1, 1)
    for y in range(height):
        ratio = y / denominator
        color = tuple(
            round(start + (end - start) * ratio)
            for start, end in zip(top_color, bottom_color)
        )
        draw.line((0, y, width, y), fill=color)
    return image

# --- 3. SCANNER LOGIC STATE ---
VALID_MODELS = [
    'gemini-3.5-flash-lite',
    'gemini-3.1-flash-lite',
    'gemini-3.5-flash',
    'gemini-2.5-flash-lite',
]
processed_messages = deque(maxlen=500)  
SONG_CACHE = [] 

# --- 4. LOGIC HELPERS ---

FUZZY_MATCH_THRESHOLD = 0.72  

_sheets_service = None

def load_local_song_fallback():
    try:
        return sorted({
            os.path.splitext(filename)[0]
            for filename in os.listdir(JACKET_FOLDER)
            if filename.lower().endswith('.jpg')
        }, key=str.casefold)
    except OSError:
        logger.exception("Failed to load local jacket names for autocomplete fallback")
        return []

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
        range_name = f"'{INPUT_TAB_NAME}'!A5:A2500"
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])
        
        temp_cache = []
        for row in rows:
            if row:
                raw_name = str(row[0]).strip()
                clean_name = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_name).strip()
                if clean_name and clean_name not in temp_cache:
                    temp_cache.append(clean_name)
                    
        SONG_CACHE = temp_cache
        logger.info(f"Loaded {len(SONG_CACHE)} clean songs into autocomplete cache.")
    except Exception as e:
        logger.exception("Failed to fetch songs for cache")
        if not SONG_CACHE:
            SONG_CACHE = load_local_song_fallback()
            logger.info(f"Using {len(SONG_CACHE)} local jacket names for autocomplete.")

def map_difficulty(text):
    t = str(text).upper().strip()
    if any(x in t for x in ["INS", "INSIGHT", "INDIGO"]): return "INS"
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
                sheet_song = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip().lower()
                
                if sheet_song == ai_song: 
                    if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                        row_index = i + 1
                        matched_song_name = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip()
                        break
            if row_index != -1: break

        # --- STEP 2: FUZZY FALLBACK ---
        if row_index == -1:
            for i, row in enumerate(rows):
                for cell in row[:3]:
                    raw_sheet_song = str(cell).strip()
                    sheet_song = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip().lower()
                    
                    if not sheet_song: continue
                    if sheet_song in ai_song or ai_song in sheet_song:
                        if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                            row_index = i + 1
                            matched_song_name = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip()
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
                    sheet_song_clean = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip()
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
            b50_result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=DASHBOARD_B50_RANGE
            ).execute()
            b50_rows = b50_result.get('values', [])
            for b50_row in b50_rows:
                if len(b50_row) >= 5:
                    b50_title = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', str(b50_row[2])).strip().lower()
                    if b50_title == matched_song_name.lower() or b50_title in matched_song_name.lower() or matched_song_name.lower() in b50_title:
                        try:
                            ptt_val = float(b50_row[4])
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
    matches = [
        song for song in SONG_CACHE
        if current.casefold() in song.casefold() and len(song) <= 100
    ]
    return [app_commands.Choice(name=match, value=match) for match in matches[:25]]

@bot.tree.command(name="submit", description="Manually upload an Arcaea score to the spreadsheet")
@app_commands.describe(
    song="Search for the song name", 
    difficulty="Select the difficulty", 
    score="Type your score (e.g. 9982341)"
)
@app_commands.choices(difficulty=[
    app_commands.Choice(name="Insight (INS)", value="INS"),
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


@bot.tree.command(name="b50", description="Generate your Arcaea B50 and Potential Stats")
@app_commands.describe(
    username="The name you want displayed on the image",
    current_ptt="Your current in-game Potential (e.g. 12.50)"
)
async def b50_slash(interaction: discord.Interaction, current_ptt: float = None, username: str = None):
    display_name = username if username else interaction.user.display_name
    await interaction.response.defer() 
    
    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=DASHBOARD_B50_RANGE
        ).execute()
        rows = result.get('values', [])

        if not rows:
            return await interaction.followup.send(f"No data found in the spreadsheet ({DASHBOARD_B50_RANGE}).")

        normalized_rows = [(row + [''] * 5)[:5] for row in rows[:BEST_SCORE_COUNT]]
        df = pd.DataFrame(normalized_rows, columns=['Rank', 'Level', 'Title', 'Score', 'PTT'])
        df['PTT'] = pd.to_numeric(df['PTT'], errors='coerce').fillna(0)
        
        b50_sum = df['PTT'].head(BEST_SCORE_COUNT).sum()
        top_10_sum = df['PTT'].head(TOP_SCORE_COUNT).sum()
        calculated_ptt = (b50_sum + top_10_sum) / (BEST_SCORE_COUNT + TOP_SCORE_COUNT)
        gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        font_title = load_font(16)
        font_score = load_font(18)
        font_ptt = load_font(20)
        font_difficulty = load_font(20)
        font_header = load_font(42)
        font_stats = load_font(22)
        font_date = load_font(16)

        canvas_w = (
            (SIDE_PADDING * 2)
            + (JACKET_SIZE * COLUMNS)
            + (HORIZONTAL_GAP * (COLUMNS - 1))
            + DIFFICULTY_BADGE_RADIUS
        )
        canvas_h = HEADER_SPACE + MARGIN + ((JACKET_SIZE + BOTTOM_TEXT_SPACE) * ROWS) + (VERTICAL_GAP * ROWS)
        canvas = create_vertical_gradient(canvas_w, canvas_h, BACKGROUND_TOP, BACKGROUND_BOTTOM)
        draw = ImageDraw.Draw(canvas)

        draw.text((SIDE_PADDING, 20), f"{display_name}'s Best 50", fill=(255, 255, 255), font=font_header)
        displayed_ptt = current_ptt if current_ptt is not None else calculated_ptt
        displayed_ptt = math.floor(displayed_ptt * 1000) / 1000
        stats_text = f"PTT: {displayed_ptt:.3f}"
        
        draw.text((SIDE_PADDING, 75), stats_text, fill=(255, 215, 0), font=font_stats)
        draw.text((SIDE_PADDING, 115), f"Generated on: {gen_date}", fill=(150, 150, 150), font=font_date)

        if os.path.exists(PLACEHOLDER_PATH):
            placeholder_img = Image.open(PLACEHOLDER_PATH).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
        else:
            placeholder_img = Image.new('RGB', (JACKET_SIZE, JACKET_SIZE), (40, 40, 50))

        for index, row in df.iterrows():
            if index >= BEST_SCORE_COUNT: break
            col, row_idx = index % COLUMNS, index // COLUMNS
            x = SIDE_PADDING + col * (JACKET_SIZE + HORIZONTAL_GAP)
            y = HEADER_SPACE + MARGIN + row_idx * (JACKET_SIZE + BOTTOM_TEXT_SPACE + VERTICAL_GAP)

            raw_title = str(row['Title'])
            diff_match = re.search(r'\[(INS|FTR|BYD|ETR|PRS|PST)\]', raw_title, re.IGNORECASE)
            difficulty = diff_match.group(1).upper() if diff_match else 'FTR'
            clean_title = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST)\]\s*$', '', raw_title).strip()

            jacket_path = jacket_path_for_chart(clean_title, difficulty)

            if jacket_path:
                with Image.open(jacket_path) as jacket_image:
                    img = jacket_image.convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
                canvas.paste(img, (x, y))
            else:
                canvas.paste(placeholder_img, (x, y))

            badge_color = DIFF_COLORS.get(difficulty, (255, 255, 255))
            badge_center_x = x + JACKET_SIZE
            badge_center_y = y
            badge_points = [
                (badge_center_x, badge_center_y - DIFFICULTY_BADGE_RADIUS),
                (badge_center_x + DIFFICULTY_BADGE_RADIUS, badge_center_y),
                (badge_center_x, badge_center_y + DIFFICULTY_BADGE_RADIUS),
                (badge_center_x - DIFFICULTY_BADGE_RADIUS, badge_center_y),
            ]
            draw.polygon(badge_points, fill=badge_color, outline=(255, 255, 255), width=2)
            level_text = str(row['Level']).strip()
            level_box = draw.textbbox((0, 0), level_text, font=font_difficulty)
            level_w = level_box[2] - level_box[0]
            level_h = level_box[3] - level_box[1]
            level_x = badge_center_x - level_w / 2
            level_y = badge_center_y - level_h / 2 - level_box[1]
            draw.text((level_x, level_y), level_text, fill=(255, 255, 255), font=font_difficulty)

            title_text = clean_title
            max_w = JACKET_SIZE - 5 
            
            if draw.textlength(title_text, font=font_title) > max_w:
                while draw.textlength(title_text + "..", font=font_title) > max_w:
                    title_text = title_text[:-1]
                title_text = title_text + ".."
            
            draw.text((x, y + JACKET_SIZE + 5), title_text, fill=(200, 200, 200), font=font_title)

            draw.text((x, y + JACKET_SIZE + 25), f"{row['Score']}", fill="white", font=font_score)
            ptt_color = (255, 215, 0) if index < TOP_SCORE_COUNT else (255, 255, 255)
            draw.text((x, y + JACKET_SIZE + 48), f"PTT: {row['PTT']:.3f}", fill=ptt_color, font=font_ptt)

        with io.BytesIO() as binary:
            canvas.save(binary, 'PNG')
            binary.seek(0)
            await interaction.followup.send(file=discord.File(fp=binary, filename=f'{display_name}_b50.png'))

    except Exception as e:
        logger.exception("Error generating B50 image")
        await interaction.followup.send(f"Error generating B50: {e}")


# --- 6. BOT EVENTS ---

@bot.event
async def on_ready():
    await asyncio.to_thread(fetch_song_list)
    logger.info(f"Logged in as {bot.user}; autocomplete has {len(SONG_CACHE)} songs.")

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
            attempted_models = []
            mime_type = attachment.content_type or mimetypes.guess_type(attachment.filename)[0]
            if mime_type not in {'image/jpeg', 'image/png', 'image/webp'}:
                mime_type = 'image/jpeg'
            
            for model_name in VALID_MODELS:
                attempted_models.append(model_name)
                
                try:
                    prompt = """
                    Extract Arcaea result: Song Title | Difficulty | Score.
                    
                    DIFFICULTY RULES:
                    - DARK BLUE/INDIGO badge = INSIGHT (INS).
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
                            types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
                        ]
                    )
                    
                    ai_text = (response.text or "").replace("**", "").strip()

                    for candidate_line in ai_text.splitlines():
                        if candidate_line.count("|") < 2:
                            continue
                        parts = [p.strip() for p in candidate_line.split("|")]
                        if len(parts) >= 3:
                            raw_title = parts[0]
                            raw_diff = parts[1]
                            clean_score_only = re.sub(r'\D', '', parts[2])

                            if clean_score_only.isdigit() and 9000000 <= int(clean_score_only) <= 11000000:
                                extracted_data = [raw_title, raw_diff, clean_score_only]
                                break

                    if extracted_data:
                        logger.info(f"Model '{model_name}' successfully read '{attachment.filename}'.")
                        break

                    logger.warning(
                        f"Model '{model_name}' returned no valid Arcaea result for '{attachment.filename}'; trying fallback."
                    )
                except Exception as e:
                    logger.warning(f"Model '{model_name}' failed to read image: {e}")
                    continue

            if extracted_data:
                title, diff, ai_score = extracted_data[0], extracted_data[1], extracted_data[2]
                
                title = re.sub(r'(?i)\s*\[(INS|FTR|ETR|BYD|PRS|PST|INSIGHT|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', title).strip()
                
                await status_msg.edit(content=f"Uploading **{title}** to spreadsheet...")
                res = update_score_in_sheet(title, diff, ai_score)
                if res != "SKIP": 
                    report.append(res)
                    
            else:
                report.append(
                    "Image could not be read after trying all fallback models: "
                    + ", ".join(attempted_models)
                )

        if report:
            await status_msg.edit(content="**Update Summary:**\n" + "\n".join(report))
        else:
            await status_msg.delete()

# --- RUN BOT ---
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
