# Freelance Task Bot — Setup Guide

## Requirements
- Python 3.9+
- A Telegram account

---

## Step 1 — Create your bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g. `My Task Bot`) and username (e.g. `mytaskbot`)
4. BotFather gives you a **token** like: `7123456789:AAHxxx...`
5. Copy it

---

## Step 2 — Get your Admin Telegram ID

1. Open Telegram and search for **@userinfobot**
2. Send `/start`
3. It replies with your numeric **ID** (e.g. `123456789`)
4. Copy it

---

## Step 3 — Configure the bot

Open `bot.py` and fill in lines 20–21:

```python
BOT_TOKEN = "7123456789:AAHxxx..."   # paste your token here
ADMIN_ID  = 123456789                # paste your numeric ID here
```

---

## Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 5 — Run

```bash
python bot.py
```

---

## How it works

### Client flow
1. `/start` → **Post a Task**
2. Enter title → description → payment → category
3. Task appears in the Available list

### Freelancer flow
1. `/start` → **Available Tasks**
2. Click **Take this task** — task is locked to that freelancer
3. Go to **My Tasks** → **Submit completed work**
4. Send a screenshot photo
5. Admin is notified automatically

### Admin flow
1. Receive notification when a task is submitted
2. `/start` → **Review Queue** — see screenshot + task details
3. Click **Approve & Pay** or **Reject**
   - Approve: freelancer gets a payment notification, task marked as paid
   - Reject: enter a reason, freelancer is notified to resubmit

---

## Database

Tasks are stored in `tasks.db` (SQLite) — no external database needed.

## Commands
- `/start` — main menu
- `/cancel` — cancel current operation

---

## Hosting (optional)
To keep the bot running 24/7, deploy on any VPS or cloud server:
- [Railway.app](https://railway.app) — free tier available
- [Render.com](https://render.com) — free tier available  
- Any Linux VPS with `nohup python bot.py &` or a systemd service
