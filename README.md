# Arcaea AI Score Scraper & B50 Generator

A Discord bot for tracking Arcaea scores with the version 7.0 B50 system. It uses Google Gemini to read result screenshots, writes scores to the KR Consultant Google Sheet, and renders a Best 50 image with local song jackets.

<img width="480" height="440" alt="Bot-ezgif com-crop" src="https://github.com/user-attachments/assets/7b1cdc5f-f114-4f92-935a-813229d9d201" />

# Example B50
<img width="988" height="2580" alt="tainnation_b50" src="https://github.com/user-attachments/assets/c6e9f3af-1def-419c-9ebc-fc176e7dcdb0" />

Note: This bot is currently intended only for personal server use. It can scan result images posted directly by users or via automated Discord webhooks.

## Spreadsheet Template
This project relies on a fan made Google Sheets layout, specifically, the KR Consultant Sheet, for Version 7.0 and beyond:
* KR Consultant Sheet: https://docs.google.com/spreadsheets/d/1hDDM3RFr5YLY9TyUYS85tgGAs_Q3f_ftFUJGwg1q1Vc/copy?usp=sharing
* Arcaea 컨설턴트 시트 Discord: https://discord.gg/GZw4zJgnus

## Features
* Reads song title, difficulty, and score from Arcaea result screenshots.
* Supports PST, PRS, FTR, ETR, BYD, and the version 7.0 INS difficulty.
* Updates the matching chart in the configured Google Sheet.
* Provides song autocomplete for the `/submit` command.
* Renders 50 plays in a 5-column by 10-row layout.
* Displays colored difficulty diamonds and gold potential values for the top 10 plays.
* Supports difficulty-specific jacket artwork with automatic fallback to the normal jacket.
* Tries multiple Gemini models when a model is unavailable, rate-limited, or returns an invalid result.

# Commands
/b50
/submit
(Pretty Self Explanatory)

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
SPREADSHEET_ID=your_google_spreadsheet_id

INPUT_TAB_NAME=점수 입력 [Score Input]
DASHBOARD_TAB_NAME=대시보드 [Dashboard]
```

### 4. Google Credentials
1. Go to the [Google Cloud Console Service Accounts Page](https://console.cloud.google.com/projectselector2/iam-admin/serviceaccounts).
2. Create a service account (or select an existing one) and generate a new **JSON key**.
3. Download the key file, rename it to `credentials.json`, and place it in the root directory of this project.
4. Open your Google Sheet, click **Share**, and give your service account's `client_email` address **Editor** permissions.

### 5. Assets
Ensure you have a `jackets/` folder containing `.jpg` artwork files named after the songs (NOTE SOME JACKETS ARE WRONG), and a `placeholder.png` file for missing jackets.

### 6. Run the bot
```bash
python bot.py
```




### Example of simple IOS webhook shortcut

<img width="1700" height="856" alt="image" src="https://github.com/user-attachments/assets/3161864a-22be-404c-88d3-e4b09b19c287" />
