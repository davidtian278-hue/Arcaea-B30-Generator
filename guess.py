import discord
from discord.ext import commands
from discord import app_commands
import io
import random
import os
from PIL import Image
import asyncio

# --- 1. CONFIGURATION ---
DISCORD_TOKEN = 'MTQ4MDk5NjMxMDI1NjQ1MTcxNg.GPRHI2.9PjkSpqoQYQ8YW3g940I1DIgiuJedlOdKUkz_w'
JACKET_FOLDER = "jackets" # Place your .jpg or .png files here

intents = discord.Intents.default()
intents.message_content = True  # MUST BE ON IN PORTAL
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

current_games = {}

# --- 2. IMAGE LOGIC ---
def process_guess_image(image_path):
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    side = 200
    if w < side or h < side: return img
    x = random.randint(0, w - side)
    y = random.randint(0, h - side)
    cropped = img.crop((x, y, x + side, y + side))
    final = cropped.resize((400, 400), Image.LANCZOS)
    b = io.BytesIO()
    final.save(b, format='PNG')
    b.seek(0)
    return b

# --- 3. GAME LOGIC ---
async def start_new_game(ctx):
    global current_games
    cid = ctx.channel.id

    if cid in current_games:
        return await ctx.send("⚠️ Game already running!")

    files = [f for f in os.listdir(JACKET_FOLDER) if f.lower().endswith(('.jpg', '.png'))]
    chosen = random.choice(files)
    ans_raw = os.path.splitext(chosen)[0]
    ans_clean = ans_raw.lower().strip()
    
    current_games[cid] = {"ans": ans_clean, "raw": ans_raw}
    print(f"[SYSTEM] Game started in {ctx.guild.name}. Answer: {ans_raw}")

    try:
        img_data = process_guess_image(os.path.join(JACKET_FOLDER, chosen))
        await ctx.send("🎮 **Guess the Song!** (15s)", file=discord.File(img_data, "guess.png"))
        
        await asyncio.sleep(15)
        
        if cid in current_games and current_games[cid]["ans"] == ans_clean:
            print(f"[TIMER] Time up for {ans_raw} in {ctx.guild.name}")
            await ctx.channel.send(f"⏰ **Time's up!** It was: **{ans_raw}**")
            del current_games[cid]
    except Exception as e:
        print(f"[ERROR] {e}")
        if cid in current_games: del current_games[cid]

@bot.hybrid_command(name="guess")
async def guess(ctx):
    await start_new_game(ctx)

@bot.event
async def on_message(message):
    if message.author.bot: return

    # DEBUG: This prints every message the bot sees to your computer screen
    if message.channel.id in current_games:
        print(f"[INPUT] {message.author}: {message.content}")
        
        guess = message.content.lower().strip()
        if guess == current_games[message.channel.id]["ans"]:
            raw = current_games[message.channel.id]["raw"]
            del current_games[message.channel.id]
            print(f"[WIN] {message.author} guessed {raw}!")
            await message.reply(f"🎉 **Correct!** It was **{raw}**!")
            return

    await bot.process_commands(message)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Monitoring {len(bot.guilds)} servers")

bot.run(DISCORD_TOKEN)