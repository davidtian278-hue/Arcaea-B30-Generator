import discord
from discord import app_commands
from discord.ext import commands
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import os
from datetime import datetime

# --- Bot Setup ---
class MyBot(commands.Bot):
    def __init__(self):
        # Explicitly enabling message_content intent to fix the Warning
        intents = discord.Intents.default()
        intents.message_content = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = MyBot()

# --- Design Configuration ---
JACKET_SIZE = 140
MARGIN = 20
HEADER_SPACE = 160 # Increased for Current PTT line
BOTTOM_TEXT_SPACE = 80
COLUMNS = 6
ROWS = 5
PLACEHOLDER_PATH = "placeholder.png"

DIFF_COLORS = {
    'FTR': (190, 80, 255),
    'BYD': (255, 60, 60),
    'ETR': (220, 150, 255),
}

@bot.tree.command(name="b30", description="Generate your Arcaea B30 and Potential Stats")
@app_commands.describe(
    username="The name you want displayed on the image",
    current_ptt="Your current in-game Potential (e.g. 12.50)"
)
async def b30_slash(interaction: discord.Interaction, current_ptt: float = None, username: str = None):
    display_name = username if username else interaction.user.display_name
    await interaction.response.send_message(f"📊 Generating B30 for **{display_name}**...", ephemeral=False)
    
    try:
        # 1. Load Data
        df = pd.read_csv('scores.csv', header=None)
        df.columns = ['Rank', 'Title', 'Difficulty', 'Level', 'Constant', 'Score', 'PTT']
        
        # 2. Stats & Date
        b30_sum = df['PTT'].head(30).sum()
        b30_avg = b30_sum / 30
        top_10_sum = df['PTT'].head(10).sum()
        hypo_max = (b30_sum + top_10_sum) / 40
        gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 3. Fonts
        try:
            font_title = ImageFont.truetype("arial.ttf", 16)
            font_score = ImageFont.truetype("arial.ttf", 18)
            font_ptt = ImageFont.truetype("arial.ttf", 20)
            font_header = ImageFont.truetype("arial.ttf", 42)
            font_stats = ImageFont.truetype("arial.ttf", 22)
            font_date = ImageFont.truetype("arial.ttf", 16)
        except:
            font_title = font_score = font_ptt = font_header = font_stats = font_date = ImageFont.load_default()

        # 4. Canvas
        canvas_w = (JACKET_SIZE + MARGIN) * COLUMNS + MARGIN
        canvas_h = HEADER_SPACE + (JACKET_SIZE + BOTTOM_TEXT_SPACE + MARGIN) * ROWS + MARGIN
        canvas = Image.new('RGB', (canvas_w, canvas_h), color=(10, 10, 15))
        draw = ImageDraw.Draw(canvas)

        # 5. Header
        draw.text((MARGIN, 20), f"{display_name}'s Best 30", fill=(255, 255, 255), font=font_header)
        
        # PTT Stats line with user-provided Current PTT
        ptt_display = f"PTT: {current_ptt:.2f}" if current_ptt is not None else "PTT: --.--"
        stats_text = f"{ptt_display}  |  B30 Avg: {b30_avg:.4f}  |  Max: {hypo_max:.4f}"
        
        draw.text((MARGIN, 75), stats_text, fill=(255, 215, 0), font=font_stats)
        draw.text((MARGIN, 115), f"Generated on: {gen_date}", fill=(150, 150, 150), font=font_date)

        # 6. Grid
        if os.path.exists(PLACEHOLDER_PATH):
            placeholder_img = Image.open(PLACEHOLDER_PATH).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
        else:
            placeholder_img = Image.new('RGB', (JACKET_SIZE, JACKET_SIZE), (40, 40, 50))

        for index, row in df.iterrows():
            if index >= 30: break
            col, row_idx = index % COLUMNS, index // COLUMNS
            x = MARGIN + col * (JACKET_SIZE + MARGIN)
            y = HEADER_SPACE + MARGIN + row_idx * (JACKET_SIZE + BOTTOM_TEXT_SPACE + MARGIN)

            # Jacket Art
            clean_title = str(row['Title']).replace(":", "").replace("/", "").strip()
            jacket_path = f"jackets/{clean_title}.jpg"
            if os.path.exists(jacket_path):
                img = Image.open(jacket_path).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
                canvas.paste(img, (x, y))
            else:
                canvas.paste(placeholder_img, (x, y))

            # --- SMART TITLE TRUNCATION ---
            title_text = str(row['Title'])
            max_w = JACKET_SIZE - 5 
            
            if draw.textlength(title_text, font=font_title) > max_w:
                while draw.textlength(title_text + "..", font=font_title) > max_w:
                    title_text = title_text[:-1]
                title_text = title_text + ".."
            
            draw.text((x, y + JACKET_SIZE + 5), title_text, fill=(200, 200, 200), font=font_title)

            # Score & PTT
            draw.text((x, y + JACKET_SIZE + 25), f"{row['Score']}", fill="white", font=font_score)
            ptt_color = DIFF_COLORS.get(row['Difficulty'], (255, 255, 255))
            draw.text((x, y + JACKET_SIZE + 48), f"PTT: {row['PTT']:.4f}", fill=ptt_color, font=font_ptt)

        # 7. Output
        with io.BytesIO() as binary:
            canvas.save(binary, 'PNG')
            binary.seek(0)
            await interaction.followup.send(file=discord.File(fp=binary, filename=f'{display_name}_b30.png'))

    except Exception as e:
        print(f"Error: {e}")
        await interaction.followup.send(f"❌ Error: {e}")

bot.run('MTQ4MDk5NjMxMDI1NjQ1MTcxNg.GPRHI2.9PjkSpqoQYQ8YW3g940I1DIgiuJedlOdKUkz_w')



# GUESSING GAME


# --- 1. CONFIGURATION ---
DISCORD_TOKEN = 'MTQ4MDk5NjMxMDI1NjQ1MTcxNg.GPRHI2.9PjkSpqoQYQ8YW3g940I1DIgiuJedlOdKUkz_w'
# ... (Keep your existing Google/Gemini keys here)

# New Config for Game
JACKET_FOLDER = "jackets" # Folder where your song art is stored
current_game = {} # To track {channel_id: "correct_song_name"}

# --- 2. GAME LOGIC ---

def pixelate_image(image_path, pixel_size=15):
    """Opens an image and turns it into a few blurry pixels."""
    img = Image.open(image_path)
    # Resize down to tiny size, then back up to look pixelated
    small = img.resize((pixel_size, pixel_size), resample=Image.BILINEAR)
    result = small.resize(img.size, Image.NEAREST)
    
    img_byte_arr = io.BytesIO()
    result.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr

# --- 3. BOT COMMANDS ---

@bot.command(name="guess")
async def guess_game(ctx):
    """Starts a new guessing game."""
    global current_game
    
    # 1. Get song list from your sheet
    service = build('sheets', 'v4', credentials=service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES))
    result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=f"'{SHEET_NAME}'!A1:A2500").execute()
    songs = [row[0] for row in result.get('values', []) if row]
    
    # 2. Pick a random song that has a matching image file
    valid_songs = [s for s in songs if os.path.exists(os.path.join(JACKET_FOLDER, f"{s}.jpg"))]
    
    if not valid_songs:
        await ctx.send("❌ No jacket images found in the 'jackets' folder!")
        return

    chosen_song = random.choice(valid_songs)
    current_game[ctx.channel.id] = chosen_song.lower()

    # 3. Pixelate and send
    image_path = os.path.join(JACKET_FOLDER, f"{chosen_song}.jpg")
    pixel_data = pixelate_image(image_path, pixel_size=10) # 10x10 pixels is very hard!
    
    file = discord.File(fp=pixel_data, filename="guess.png")
    await ctx.send("🎮 **Guess the Song!** Type the name of this song:", file=file)

# --- 4. UPDATED ON_MESSAGE ---

@bot.event
async def on_message(message):
    global current_game
    if message.author.bot: return

    # Check if a game is active in this channel
    if message.channel.id in current_game:
        answer = current_game[message.channel.id]
        if message.content.lower().strip() == answer:
            await message.reply(f"🎉 **Correct!** It was **{answer.title()}**!")
            del current_game[message.channel.id]
            return

    # ... (Keep your existing score-scanning logic here)
    await bot.process_commands(message) 

bot.run(DISCORD_TOKEN)