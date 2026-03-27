import discord
from discord.ext import commands
from discord import app_commands
import google.generativeai as genai
from googleapiclient.discovery import build
from google.oauth2 import service_account
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import os

# --- 1. CONFIGURATION ---
# Load the keys from the .env file (override=True ignores old cached passwords)
load_dotenv(override=True) 

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_FILE = 'credentials.json'

# Tab Names
SHEET_NAME = "Score Input" # For the AI Scanner
B30_TAB_NAME = "b30"       # For the B30 Generator

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# --- INITIALIZATION ---
genai.configure(api_key=GEMINI_API_KEY)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

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

# --- 3. SCANNER LOGIC STATE ---
# Prioritize newer flash models to avoid 404s, falling back as needed
VALID_MODELS = [
    'gemini-2.5-flash',
    'gemini-3.0-flash', 
    'gemini-1.5-flash',
    'gemini-1.5-pro'
]
processed_messages = set() 
SONG_CACHE = [] # Stores spreadsheet songs for autocomplete

# --- 4. LOGIC HELPERS ---

def fetch_song_list():
    """Downloads the song list from Sheets so the bot can search it quickly."""
    global SONG_CACHE
    try:
        service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES))
        range_name = f"'{SHEET_NAME}'!A1:A2500" 
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        rows = result.get('values', [])
        
        temp_cache = []
        for row in rows:
            if row:
                raw_name = str(row[0]).strip()
                # Scrub the difficulty tag out for a clean drop-down
                clean_name = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_name).strip()
                # Only add if it's not already in the list (prevents duplicates)
                if clean_name and clean_name not in temp_cache:
                    temp_cache.append(clean_name)
                    
        SONG_CACHE = temp_cache
        print(f"Loaded {len(SONG_CACHE)} clean songs into autocomplete cache.")
    except Exception as e:
        print(f"Failed to fetch songs for cache: {e}")

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
        if not rows: return "Sheet Error: No data found."

        matched_song_name = song_target # Default fallback

        # --- STEP 1: STRICT EXACT MATCH ---
        row_index = -1
        for i, row in enumerate(rows):
            for cell in row[:3]:
                # Grab the sheet name and scrub it so it matches our clean drop-down name
                raw_sheet_song = str(cell).strip()
                sheet_song = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', raw_sheet_song).strip().lower()
                
                if sheet_song == ai_song: 
                    if len(row) > 3 and map_difficulty(row[3]) == final_diff:
                        row_index = i + 1
                        # Save the cleaned name for the Discord message
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

        if row_index == -1:
            return f"No match for **{song_target}** on **{final_diff}**."

        clean_score = str(score_value).replace(",", "").strip()

        # Update Column H
        update_range = f"'{SHEET_NAME}'!H{row_index}"
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=update_range,
            valueInputOption="USER_ENTERED", body={'values': [[clean_score]]}
        ).execute()

        # --- Fetch the play potential (PTT) from the b30 tab by matching song title ---
        ptt_display = ""
        try:
            b30_result = service.spreadsheets().values().get(
                spreadsheetId=SPREADSHEET_ID, range=f"'{B30_TAB_NAME}'!B8:F37"
            ).execute()
            b30_rows = b30_result.get('values', [])
            for b30_row in b30_rows:
                # b30 columns: Rank, Level, Title, Score, PTT (indices 0-4)
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
        return f"**{matched_song_name}** [{final_diff}] -> **{clean_score}**{ptt_display}{pm_tag}"
    except Exception as e:
        return f"Sheet Error: {str(e)}"

# --- 5. SLASH COMMANDS ---

async def song_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Filters the cached song list as the user types."""
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


@bot.tree.command(name="hikari", description="Translate your message into Hikari's elegant voice")
@app_commands.describe(text="The message you want Hikari to say")
async def hikari_speak(interaction: discord.Interaction, text: str):
    await interaction.response.defer()
    
    prompt = f"""
    Rewrite the following text in the persona of Hikari from the rhythm game Arcaea. 
    Hikari is gentle, ethereal, somewhat formal, and deeply connected to memories, glass, skies, and light. 
    She speaks calmly, with a sense of wonder, grace, and sometimes a hint of melancholy. 
    Keep the core meaning of the original message entirely intact, but change the tone and vocabulary to match her perfectly. 
    Do not add conversational filler like 'Here is your translation', just output her exact words.
    
    Original text: {text}
    """
    
    hikari_text = None
    
    for model_name in VALID_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            hikari_text = response.text.strip()
            break
        except:
            continue
            
    if hikari_text:
        await interaction.followup.send(f"{hikari_text}")
    else:
        await interaction.followup.send("*The light faded...* (Error: None of the AI models are currently responding. Check your API limits!)")


@bot.tree.command(name="b30", description="Generate your Arcaea B30 and Potential Stats")
@app_commands.describe(
    username="The name you want displayed on the image",
    current_ptt="Your current in-game Potential (e.g. 12.50)"
)
async def b30_slash(interaction: discord.Interaction, current_ptt: float = None, username: str = None):
    display_name = username if username else interaction.user.display_name
    await interaction.response.defer() 
    
    try:
        # Fetch from Google Sheets 'b30' tab
        service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES))
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

        try:
            font_title = ImageFont.truetype("arial.ttf", 16)
            font_score = ImageFont.truetype("arial.ttf", 18)
            font_ptt = ImageFont.truetype("arial.ttf", 20)
            font_header = ImageFont.truetype("arial.ttf", 42)
            font_stats = ImageFont.truetype("arial.ttf", 22)
            font_date = ImageFont.truetype("arial.ttf", 16)
        except:
            font_title = font_score = font_ptt = font_header = font_stats = font_date = ImageFont.load_default()

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
        print(f"Error: {e}")
        await interaction.followup.send(f"Error generating B30: {e}")


# --- 6. BOT EVENTS ---

@bot.event
async def on_ready():
    print(f"Bot online")
    fetch_song_list() # Load songs for autocomplete

@bot.event
async def on_message(message):
    global processed_messages
    if message.author.bot or message.id in processed_messages: return

    # Trigger scanner only if there is an image attached
    if message.attachments:
        images = [a for a in message.attachments if any(a.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg'])]
        if not images: return

        processed_messages.add(message.id)
        status_msg = await message.channel.send("Analyzing result...")
        report = []

        for attachment in images:
            img_bytes = await attachment.read()
            extracted_data = None 
            
            # Try to read the image using Gemini
            for model_name in VALID_MODELS:
                if extracted_data: break 
                
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
                    
                    # Clean up basic markdown
                    ai_text = response.text.replace("**", "").strip()
                    
                    if "|" in ai_text:
                        parts = [p.strip() for p in ai_text.split("|")]
                        if len(parts) >= 3:
                            # Keep title and difficulty raw, but strip commas/apostrophes from the score
                            raw_title = parts[0]
                            raw_diff = parts[1]
                            clean_score_only = parts[2].replace(",", "").replace("'", "").strip()
                            
                            extracted_data = [raw_title, raw_diff, clean_score_only]
                            break 
                except: continue

            if extracted_data:
                title, diff, ai_score = extracted_data[0], extracted_data[1], extracted_data[2]
                
                # Strip out accidental difficulty tags from the title string
                title = re.sub(r'(?i)\s*\[(FTR|ETR|BYD|PRS|PST|FUTURE|ETERNAL|BEYOND|PRESENT|PAST)\]\s*$', '', title).strip()
                final_diff_mapped = map_difficulty(diff)
                
                prompt_text = (
                    f"Found: **{title}** [{final_diff_mapped}] -> **{ai_score}**\n"
                    f"- `y` to accept, `n` to cancel.\n"
                    f"- Type a **number** to fix score only.\n"
                    f"- Type `Title | Diff | Score` to fix everything.\n"
                    f"*(Timeout in 60s)*"
                )
                await status_msg.edit(content=prompt_text)

                def check(m):
                    if m.author != message.author or m.channel != message.channel:
                        return False
                    
                    content = m.content.lower().strip()
                    if content in ['y', 'yes', 'n', 'no']: return True
                    if content.replace(',', '').isdigit(): return True
                    if "|" in content: return True
                    return False

                try:
                    confirm_msg = await bot.wait_for('message', check=check, timeout=60.0)
                    user_response = confirm_msg.content.strip()
                    user_lower = user_response.lower()
                    
                    final_title = title
                    final_diff = diff
                    final_score = ai_score
                    should_upload = False

                    if user_lower in ['y', 'yes']:
                        should_upload = True
                    elif user_lower in ['n', 'no']:
                        should_upload = False
                    elif "|" in user_response:
                        parts = [p.strip() for p in user_response.split("|")]
                        if len(parts) >= 3:
                            final_title = parts[0]
                            final_diff = parts[1]
                            final_score = parts[2].replace(',', '')
                            should_upload = True
                        else:
                            report.append(f"Invalid override format for **{title}**. Skipped.")
                            should_upload = False
                    else:
                        final_score = user_response.replace(',', '')
                        should_upload = True

                    if should_upload:
                        try: 
                            await confirm_msg.delete() 
                        except: 
                            pass 
                        
                        await status_msg.edit(content=f"Uploading to spreadsheet...")
                        res = update_score_in_sheet(final_title, final_diff, final_score)
                        if res != "SKIP": report.append(res)
                    else:
                        if "|" not in user_response:
                            report.append(f"Canceled upload for **{title}**.")
                        
                except asyncio.TimeoutError:
                    report.append(f"Timed out waiting for confirmation for **{title}**.")
                    
            else:
                report.append("Image could not be read. (Models may be exhausted or rate-limited)")

        if report:
            await status_msg.edit(content="**Update Summary:**\n" + "\n".join(report))
        else:
            await status_msg.delete()
            
        if len(processed_messages) > 100:
            processed_messages.clear()

# --- RUN BOT ---
bot.run(DISCORD_TOKEN)
