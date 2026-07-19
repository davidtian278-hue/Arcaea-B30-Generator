# Arcaea AI Score Scraper & B30 Generator

A custom Discord bot designed to automate Arcaea score tracking and generate B30 image. It uses Google's Gemini AI to scan score screenshots directly from Discord, logs them into a Google Spreadsheet, and generates the B30 image.

<img width="480" height="440" alt="Bot-ezgif com-crop" src="https://github.com/user-attachments/assets/7b1cdc5f-f114-4f92-935a-813229d9d201" />

Note: This bot is currently intended only for personal server use. It can scan result images posted directly by users or via automated Discord webhooks.

## Spreadsheet Template
This project relies on a fan made Google Sheets layout, specifically, the Lite version of the KR Consultant Sheet:
* KR Consultant Sheet: https://docs.google.com/spreadsheets/d/1hDDM3RFr5YLY9TyUYS85tgGAs_Q3f_ftFUJGwg1q1Vc/copy?usp=sharing
* Arcaea 컨설턴트 시트 Discord: https://discord.gg/GZw4zJgnus

## Features
* AI Score Scanning: Reads result screenshots sent by users or webhooks and automatically extracts song titles, difficulties, and scores.
* Google Sheets Integration: Automatically logs valid scores directly to your spreadsheet.
* B30 Image Generation: Renders a Best 30 showcase image using tracked scores and local jacket artwork.

## Tech Stack
* Python 3.x
* discord.py
* Google Generative AI
* Google Sheets API
* Pillow
* Pandas

## Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/davidtian278-hue/Arcaea-B30-Generator.git
cd Arcaea-B30-Generator
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory:

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
SPREADSHEET_ID=your_google_sheet_id
```

### 4. Google Credentials
1. Go to the [Google Cloud Console Service Accounts Page](https://console.cloud.google.com/projectselector2/iam-admin/serviceaccounts).
2. Create a service account (or select an existing one) and generate a new **JSON key**.
3. Download the key file, rename it to `credentials.json`, and place it in the root directory of this project.
4. Open your Google Sheet, click **Share**, and give your service account's `client_email` address **Editor** permissions.

### 5. Assets
Ensure you have a `jackets/` folder containing `.jpg` artwork files named after the songs (NOTE SOME JACKETS ARE WRONG), and a `placeholder.png` file for missing jackets.

### 6. Spreadsheet Setup
Make sure you remove the excess text in the sheet tabs so they are just:
* **`Score Input`** - Where raw score logs are written.
* **`B30`** - Where top scores and rating calculations are pulled from.
* <img width="400" height="114" alt="image" src="https://github.com/user-attachments/assets/2bb30ede-85cd-4ec5-abab-67989c7c163c" />

### 7. Run the bot
```bash
python bot.py
```




### Example of simple IOS webhook shortcut

<img width="1700" height="856" alt="image" src="https://github.com/user-attachments/assets/3161864a-22be-404c-88d3-e4b09b19c287" />

