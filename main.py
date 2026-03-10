import discord
from discord import app_commands
from discord.ext import commands
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import io
import os

# --- Bot Setup ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # This registers the / commands with Discord
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = MyBot()

# --- Design Configuration ---
JACKET_SIZE = 140
MARGIN = 20
HEADER_SPACE = 120    # Room for the Average & Max PTT at the top
BOTTOM_TEXT_SPACE = 80 # Room for Title, Score, and PTT below each jacket
COLUMNS = 6
ROWS = 5
PLACEHOLDER_PATH = "placeholder.png"

# Arcaea Difficulty Colors
DIFF_COLORS = {
    'FTR': (190, 80, 255),  # Purple
    'BYD': (255, 60, 60),   # Red
    'ETR': (0, 220, 255),   # Cyan
}

@bot.tree.command(name="b30", description="Generate your Arcaea B30 and Potential Stats")
async def b30_slash(interaction: discord.Interaction):
    # ephemeral=False ensures everyone in the channel can see the result
    await interaction.response.send_message("📊 Calculating Potential and generating grid...", ephemeral=False)
    
    try:
        # 1. Load the spreadsheet data
        # Structure: Rank, Title, Difficulty, Level, Constant, Score, PTT
        df = pd.read_csv('scores.csv', header=None)
        df.columns = ['Rank', 'Title', 'Difficulty', 'Level', 'Constant', 'Score', 'PTT']
        
        # 2. Potential Calculations
        b30_sum = df['PTT'].head(30).sum()
        b30_avg = b30_sum / 30
        
        top_10_sum = df['PTT'].head(10).sum()
        hypo_max = (b30_sum + top_10_sum) / 40

        # 3. Setup Fonts (Using Arial - standard on Windows)
        try:
            font_title = ImageFont.truetype("arial.ttf", 16)
            font_score = ImageFont.truetype("arial.ttf", 18)
            font_ptt = ImageFont.truetype("arial.ttf", 20)
            font_header = ImageFont.truetype("arial.ttf", 36)
            font_sub = ImageFont.truetype("arial.ttf", 24)
        except:
            font_title = font_score = font_ptt = font_header = font_sub = ImageFont.load_default()

        # 4. Create the Canvas
        canvas_w = (JACKET_SIZE + MARGIN) * COLUMNS + MARGIN
        canvas_h = HEADER_SPACE + (JACKET_SIZE + BOTTOM_TEXT_SPACE + MARGIN) * ROWS + MARGIN
        canvas = Image.new('RGB', (canvas_w, canvas_h), color=(10, 10, 15)) # Deep dark background
        draw = ImageDraw.Draw(canvas)

        # 5. Draw Header Statistics
        draw.text((MARGIN, 25), f"B30 Average: {b30_avg:.4f}", fill=(255, 255, 255), font=font_header)
        draw.text((MARGIN, 70), f"Hypothetical Max PTT: {hypo_max:.4f}", fill=(255, 215, 0), font=font_sub)

        # 6. Prepare Placeholder Image
        if os.path.exists(PLACEHOLDER_PATH):
            placeholder_img = Image.open(PLACEHOLDER_PATH).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
        else:
            placeholder_img = Image.new('RGB', (JACKET_SIZE, JACKET_SIZE), (40, 40, 50))

        # 7. Draw the 5x6 Grid
        for index, row in df.iterrows():
            if index >= 30: break
            
            col = index % COLUMNS
            row_idx = index // COLUMNS
            
            x = MARGIN + col * (JACKET_SIZE + MARGIN)
            y = HEADER_SPACE + MARGIN + row_idx * (JACKET_SIZE + BOTTOM_TEXT_SPACE + MARGIN)

            # --- Paste Jacket ---
            clean_title = str(row['Title']).replace(":", "").replace("/", "").strip()
            jacket_path = f"jackets/{clean_title}.jpg"
            
            if os.path.exists(jacket_path):
                try:
                    img = Image.open(jacket_path).convert("RGB").resize((JACKET_SIZE, JACKET_SIZE))
                    canvas.paste(img, (x, y))
                except:
                    canvas.paste(placeholder_img, (x, y))
            else:
                canvas.paste(placeholder_img, (x, y))

            # --- Draw Text Information ---
            # Song Title
            title_text = str(row['Title'])
            if len(title_text) > 16: title_text = title_text[:14] + ".."
            draw.text((x, y + JACKET_SIZE + 5), title_text, fill=(200, 200, 200), font=font_title)

            # Score
            draw.text((x, y + JACKET_SIZE + 25), f"{row['Score']}", fill="white", font=font_score)
            
            # Potential (Colorful based on Difficulty)
            ptt_color = DIFF_COLORS.get(row['Difficulty'], (255, 255, 255))
            draw.text((x, y + JACKET_SIZE + 48), f"PTT: {row['PTT']:.4f}", fill=ptt_color, font=font_ptt)

        # 8. Send the result back to Discord
        with io.BytesIO() as binary:
            canvas.save(binary, 'PNG')
            binary.seek(0)
            # Use followup because the first response was the "Generating" message
            await interaction.followup.send(file=discord.File(fp=binary, filename='b30_report.png'))

    except Exception as e:
        print(f"Error: {e}")
        await interaction.followup.send(f"❌ Error generating report: {e}")

# IMPORTANT: Put your token here
bot.run('MTQ4MDk5NjMxMDI1NjQ1MTcxNg.GPRHI2.9PjkSpqoQYQ8YW3g940I1DIgiuJedlOdKUkz_w')