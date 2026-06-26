# 🤖 Price Monitor Telegram Bot

A Telegram bot that tracks product prices across Amazon and Google Shopping,
stores price history in PostgreSQL, and alerts users when prices drop.

## 🚀 Features

- Compare prices across Amazon & Google Shopping in real time
- Track individual products and get notified on price drops
- Bulk-add up to 20 specific products or 50 products by category at once
- Daily automated price checks with Telegram alerts
- Excel reports with price history and trend charts, generated on demand
- Rate limiting, per-user tracking limits, and daily API quota protection

## 🛠️ Tech Stack

- **Python 3.14**
- **aiogram** — Telegram Bot framework with FSM for multi-step dialogs
- **PostgreSQL + SQLAlchemy** — Database
- **OpenPyXL** — Excel reports with charts
- **APScheduler** — Daily price check automation
- **OpenWebNinja API** — Amazon & Google Shopping data

## 📊 What It Tracks

| Field | Description |
|-------|-------------|
| Product Name | User-specified or category-based |
| Source | Amazon, Walmart, Best Buy, eBay, etc. |
| Price | Current price ($) |
| Rating / Reviews | Product rating and review count |
| Price History | Logged on every check for trend analysis |

## 🤖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and main menu |
| `/compare [product]` | Compare prices right now |
| `/track [product]` | Start tracking a single product |
| `/bulk_track` | Add multiple products via guided dialog |
| `/list` | View all tracked products |
| `/remove [product]` | Stop tracking a specific product |
| `/remove_all` | Stop tracking everything |
| `/report` | Get an Excel report sent to chat |
| `/help` | Show available commands |

## ⚙️ Installation

```bash
git clone https://github.com/VanguardXs/price-monitor-bot.git
cd price-monitor-bot
pip install -r requirements.txt
```

Create a `.env` file:
TELEGRAM_BOT_TOKEN=your_bot_token

OPENWEBNINJA_API_KEY=your_api_key

DB_HOST=localhost

DB_PORT=5432

DB_NAME=pricebot_db

DB_USER=your_db_user

DB_PASSWORD=your_db_password

DAILY_API_LIMIT=90

## 🔧 Usage

**Initialize the database:**
```bash
python -c "from database.db import init_db; init_db()"
```

**Run the bot:**
```bash
python -m bot.main
```

**Run the daily price-check scheduler:**
```bash
python -m scheduler.tasks
```

**Generate an Excel report manually:**
```bash
python -c "from reports.excel_report import generate_report; generate_report()"
```

## 🔐 Security

- All secrets stored in environment variables, never hardcoded
- SQLAlchemy ORM used throughout — no raw SQL, no injection risk
- Per-user rate limiting and tracking limits (max 1000 products/user)
- Daily API quota tracking to prevent exceeding provider limits
- User input sanitized and length-limited before storage or display