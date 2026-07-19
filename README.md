Arcaea B30 Generator

A custom Discord bot designed to automate Arcaea score tracking and generate Best 30 profile cards. It uses Google's Gemini AI to scan score screenshots directly from Discord, logs them into a Google Spreadsheet, and generates personalized stat images.

Note: This bot is currently intended only for personal server use. It can scan result images posted directly by users or via automated Discord webhooks.
Spreadsheet Template

This project relies on a specific Google Sheets layout, specifically the Lite version of the KR Spreadsheet (Arcaea 컨설턴트 시트):

    KR Spreadsheet: https://docs.google.com/spreadsheets/d/1hDDM3RFr5YLY9TyUYS85tgGAs_Q3f_ftFUJGwg1q1Vc/copy?usp=sharing

    Arcaea 컨설턴트 시트 Discord: https://discord.gg/GZw4zJgnus

Features

    AI Score Scanning: Reads result screenshots sent by users or webhooks and automatically extracts song titles, difficulties, and scores.

    Google Sheets Integration: Automatically logs valid scores directly to your spreadsheet.

    B30 Image Generation: Renders a Best 30 showcase image using tracked scores and local jacket artwork.

Tech Stack

    Python 3.x

    discord.py

    Google Generative AI

    Google Sheets API

    Pillow

    Pandas

Setup & Installation

    Clone the repository:

Bash

git clone https://github.com/davidtian278-hue/Arcaea-B30-Generator.git
cd Arcaea-B30-Generator

    Install dependencies:

Bash

pip install -r requirements.txt

    Environment Variables:
    Create a .env file in the root directory:

Code snippet

DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
SPREADSHEET_ID=your_google_sheet_id

    Google Credentials:
    Place your Google Service Account key file in the root directory named credentials.json.

    Assets:
    Ensure you have a jackets/ folder containing .jpg artwork files named after the songs, and a placeholder.png file for missing jackets.

    Run the bot:

Bash

python bot.py

Commands

    /submit - Manually upload an Arcaea score to the spreadsheet.

    /b30 - Generate your Best 30 image and calculate your Potential.
