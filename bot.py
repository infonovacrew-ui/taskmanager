"""
Freelance Task Bot — Telegram
Compatible with python-telegram-bot >= 22.x
"""

import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─────────────────────────────────────────────
#  CONFIG — set these in Railway Variables tab
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
DB_PATH   = os.environ.get("DB_PATH", "tasks.db")
# ─────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ──
(
    ASK_TITLE,
    ASK_DESC,
    ASK_PAY,
    ASK_CATEGORY,       # <-- now inside the conversation
    ASK_SCREENSHOT,
    ASK_REJECT_REASON,
) = range(6)

CATEGORY_ICONS = {
    "writing":  "✍️",
    "design":   "🎨",
    "research": "🔬",
    "data":     "📊",
    "other":    "📦",
}

# ═══════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id       INTEGER NOT NULL,
            client_name     TEXT    NOT NULL,
            title           TEXT    NOT NULL,
            description     TEXT    NOT NULL,
            payment         REAL    NOT NULL,
            category        TEXT    NOT NULL DEFAULT 'other',
            status          TEXT    NOT NULL DEFAULT 'available',
            freelancer_id   INTEGER,
            freelancer_name TEXT,
            screenshot_id   TEXT,
            reject_reason   TEXT,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL
        );
    """)
    con.commit()
    con.close()


def get_db():
    return sqlite3.connect(DB_PATH)


def create_task(client_id, client_name, title, desc, payment, category="other"):
    now = datetime.utcnow().isoformat()
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO tasks "
        "(client_id,client_name,title,description,payment,category,status,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (client_id, client_name, title, desc, payment, category, "available", now, now),
    )
    con.commit()
    task_id = cur.lastrowid
    con.close()
    return task_id


def get_task(task_id):
    con = get_db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None


def list_tasks(status=None, freelancer_id=None, client_id=None):
    con = get_db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if freelancer_id is not None:
        query += " AND freelancer_id=?"
        params.append(freelancer_id)
    if client_id is not None:
        query += " AND client_id=?"
        params.append(client_id)
    query += " ORDER BY id DESC"
    cur.execute(query, params)
    rows = cur.fetchall()
    con.close()
    return [dict(r) for r in rows]


def update_task(task_id, **kwargs):
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [task_id]
    con = get_db()
    con.execute(f"UPDATE tasks SET {sets} WHERE id=?", vals)
    con.commit()
    con.close()


# ═══════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════

STATUS_LABELS = {
    "available":  "🟢 Available",
    "inprogress": "🔵 In Progress",
    "review":     "🟡 Under Review",
    "approved":   "✅ Approved",
    "rejected":   "❌ Rejected",
}


def esc(text):
    if not text:
        return ""
    text = str(text)
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def fmt_task(t, show_freelancer=False):
    icon = CATEGORY_ICONS.get(t["category"], "📦")
    lines = [
        f"{icon} *{esc(t['title'])}*",
        f"_{esc(t['description'])}_",
        f"💶 Payment: *€{t['payment']:.2f}*",
        f"📂 Category: {t['category'].capitalize()}",
        f"🏷 Status: {STATUS_LABELS.get(t['status'], t['status'])}",
        f"🆔 Task \\#{t['id']}",
    ]
    if show_freelancer and t.get("freelancer_name"):
        lines.append(f"👤 Claimed by: {esc(t['freelancer_name'])}")
    if t.get("reject_reason"):
        lines.append(f"⛔ Rejection: _{esc(t['reject_reason'])}_")
    return "\n".join(lines)


def main_menu_keyboard(user_id):
    kb = [
        [InlineKeyboardButton("➕ Post a Task",              callback_data="menu_post")],
        [InlineKeyboardButton("📋 Available Tasks",          callback_data="menu_available")],
        [InlineKeyboardButton("🗂 My Tasks (Freelancer)",    callback_data="menu_my_freelancer")],
        [InlineKeyboardButton("📁 My Posted Tasks (Client)", callback_data="menu_my_client")],
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("🔔 Review Queue",    callback_data="menu_review")])
        kb.append([InlineKeyboardButton("💰 Approved & Paid", callback_data="menu_paid")])
    return InlineKeyboardMarkup(kb)


def category_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✍️ Writing",  callback_data="cat_writing"),
            InlineKeyboardButton("🎨 Design",   callback_data="cat_design"),
        ],
        [
            InlineKeyboardButton("🔬 Research", callback_data="cat_research"),
            InlineKeyboardButton("📊 Data",     callback_data="cat_data"),
        ],
        [InlineKeyboardButton("📦 Other", callback_data="cat_other")],
    ])


# ═══════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Welcome, *{esc(user.first_name)}*\\!\n\n"
        "This is the *Freelance Task Bot*\\. Here you can:\n"
        "• Post tasks as a *Client*\n"
        "• Claim and complete tasks as a *Freelancer*\n"
        "• Get paid once your work is approved\n\n"
        "Choose an option below:"
    )
    await update.message.reply_text(
        text,
        parse_mode="MarkdownV2",
        reply_markup=main_menu_keyboard(user.id),
    )


# ═══════════════════════════════════════════════
#  MENU CALLBACKS
# ═══════════════════════════════════════════════

async def menu_available(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tasks = list_tasks(status="available")
    if not tasks:
        await q.message.reply_text(
            "😴 No available tasks right now\\. Check back later\\!",
            parse_mode="MarkdownV2",
        )
        return
    for t in tasks:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"🙋 Take this task  •  €{t['payment']:.2f}",
                callback_data=f"take_{t['id']}"
            )
        ]])
        await q.message.reply_text(fmt_task(t), parse_mode="MarkdownV2", reply_markup=kb)


async def menu_my_freelancer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    tasks = list_tasks(freelancer_id=user.id)
    if not tasks:
        await q.message.reply_text("You haven't claimed any tasks yet\\.", parse_mode="MarkdownV2")
        return
    for t in tasks:
        kb = None
        if t["status"] == "inprogress":
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 Submit completed work", callback_data=f"submit_{t['id']}")
            ]])
        await q.message.reply_text(fmt_task(t), parse_mode="MarkdownV2", reply_markup=kb)


async def menu_my_client(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    tasks = list_tasks(client_id=user.id)
    if not tasks:
        await q.message.reply_text("You haven't posted any tasks yet\\.", parse_mode="MarkdownV2")
        return
    for t in tasks:
        await q.message.reply_text(fmt_task(t, show_freelancer=True), parse_mode="MarkdownV2")


async def menu_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only\\.", parse_mode="MarkdownV2")
        return
    tasks = list_tasks(status="review")
    if not tasks:
        await q.message.reply_text("✅ No pending submissions\\.", parse_mode="MarkdownV2")
        return
    for t in tasks:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve & Pay", callback_data=f"approve_{t['id']}"),
            InlineKeyboardButton("❌ Reject",         callback_data=f"reject_{t['id']}"),
        ]])
        if t.get("screenshot_id"):
            await q.message.reply_photo(
                photo=t["screenshot_id"],
                caption=fmt_task(t, show_freelancer=True),
                parse_mode="MarkdownV2",
                reply_markup=kb,
            )
        else:
            await q.message.reply_text(fmt_task(t, show_freelancer=True), parse_mode="MarkdownV2", reply_markup=kb)


async def menu_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only\\.", parse_mode="MarkdownV2")
        return
    tasks = list_tasks(status="approved")
    if not tasks:
        await q.message.reply_text("No approved tasks yet\\.", parse_mode="MarkdownV2")
        return
    lines = ["💰 *Approved & Paid Tasks*\n"]
    for t in tasks:
        lines.append(
            f"\\#{t['id']} — {esc(t['title'])} — €{t['payment']:.2f} → {esc(t.get('freelancer_name','?'))}"
        )
    await q.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


# ═══════════════════════════════════════════════
#  CREATE TASK CONVERSATION
#  Entry → title → desc → pay → category → done
# ═══════════════════════════════════════════════

async def menu_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Entry point — triggered by ➕ Post a Task button."""
    q = update.callback_query
    await q.answer()
    ctx.user_data["new_task"] = {}
    await q.message.reply_text(
        "📝 *Create a new task*\n\nStep 1 of 4 — What is the *title* of this task?",
        parse_mode="MarkdownV2",
    )
    return ASK_TITLE


async def ask_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.setdefault("new_task", {})["title"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2 of 4 — Write a *description* of what needs to be done:",
        parse_mode="MarkdownV2",
    )
    return ASK_DESC


async def ask_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_task"]["description"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 3 of 4 — What is the *payment amount* in € \\(numbers only, e\\.g\\. 25\\)?",
        parse_mode="MarkdownV2",
    )
    return ASK_PAY


async def ask_pay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        pay = float(update.message.text.strip().replace(",", "."))
        if pay <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Please enter a valid positive number \\(e\\.g\\. 25\\)\\.",
            parse_mode="MarkdownV2",
        )
        return ASK_PAY

    ctx.user_data["new_task"]["payment"] = pay
    await update.message.reply_text(
        "Step 4 of 4 — Pick a *category* for the task:",
        parse_mode="MarkdownV2",
        reply_markup=category_keyboard(),
    )
    return ASK_CATEGORY


async def ask_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handles category button press — INSIDE the conversation."""
    q = update.callback_query
    await q.answer()

    category = q.data.replace("cat_", "")
    user = q.from_user
    nt = ctx.user_data.get("new_task", {})

    # Safety check
    if not nt or "title" not in nt:
        await q.message.reply_text(
            "⚠️ Something went wrong\\. Please use /start and try again\\.",
            parse_mode="MarkdownV2",
        )
        return ConversationHandler.END

    task_id = create_task(
        client_id=user.id,
        client_name=user.full_name,
        title=nt["title"],
        desc=nt["description"],
        payment=nt["payment"],
        category=category,
    )
    ctx.user_data.pop("new_task", None)
    task = get_task(task_id)

    await q.message.reply_text(
        f"🎉 *Task posted successfully\\!*\n\n{fmt_task(task)}",
        parse_mode="MarkdownV2",
        reply_markup=main_menu_keyboard(user.id),
    )

    # Notify admin
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"📬 *New task posted*\n\n{fmt_task(task)}\n\nPosted by: {esc(user.full_name)}",
            parse_mode="MarkdownV2",
        )
    except Exception as e:
        logger.warning(f"Could not notify admin: {e}")

    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  TAKE TASK
# ═══════════════════════════════════════════════

async def take_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    task_id = int(q.data.split("_")[1])
    user = q.from_user

    task = get_task(task_id)
    if not task:
        await q.message.reply_text("⚠️ Task not found\\.", parse_mode="MarkdownV2")
        return
    if task["status"] != "available":
        await q.message.reply_text(
            "⛔ This task is no longer available\\.",
            parse_mode="MarkdownV2",
        )
        return

    update_task(task_id, status="inprogress", freelancer_id=user.id, freelancer_name=user.full_name)
    task = get_task(task_id)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 Submit completed work", callback_data=f"submit_{task_id}")
    ]])
    await q.message.reply_text(
        f"🔵 *Task claimed\\!*\n\n{fmt_task(task)}\n\nComplete the work then press the button below to submit\\.",
        parse_mode="MarkdownV2",
        reply_markup=kb,
    )

    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔵 Task \\#{task_id} *claimed* by {esc(user.full_name)} \\(ID: {user.id}\\)",
            parse_mode="MarkdownV2",
        )
    except Exception:
        pass

    try:
        await ctx.bot.send_message(
            task["client_id"],
            f"🔵 Your task *{esc(task['title'])}* was claimed by {esc(user.full_name)}\\!",
            parse_mode="MarkdownV2",
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════
#  SUBMIT WORK CONVERSATION
# ═══════════════════════════════════════════════

async def submit_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    task_id = int(q.data.split("_")[1])
    user = q.from_user

    task = get_task(task_id)
    if not task or task["freelancer_id"] != user.id:
        await q.message.reply_text("⚠️ You don't have access to this task\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END
    if task["status"] != "inprogress":
        await q.message.reply_text("⚠️ This task is not in progress\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    ctx.user_data["submit_task_id"] = task_id
    await q.message.reply_text(
        f"📸 Send a *screenshot/photo* of your completed work for task \\#{task_id}\\:\n_{esc(task['title'])}_",
        parse_mode="MarkdownV2",
    )
    return ASK_SCREENSHOT


async def receive_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task_id = ctx.user_data.get("submit_task_id")

    if not task_id:
        await update.message.reply_text("⚠️ Session expired\\. Please start again\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a *photo*\\.", parse_mode="MarkdownV2")
        return ASK_SCREENSHOT

    photo_id = update.message.photo[-1].file_id
    update_task(task_id, status="review", screenshot_id=photo_id)
    task = get_task(task_id)

    await update.message.reply_text(
        f"✅ *Submitted\\!* The admin will review your work for task \\#{task_id}\\.\n"
        "You'll be notified once it's approved or rejected\\.",
        parse_mode="MarkdownV2",
        reply_markup=main_menu_keyboard(user.id),
    )

    review_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve & Pay", callback_data=f"approve_{task_id}"),
        InlineKeyboardButton("❌ Reject",         callback_data=f"reject_{task_id}"),
    ]])
    try:
        await ctx.bot.send_photo(
            ADMIN_ID,
            photo=photo_id,
            caption=(
                f"🔔 *Review requested*\n\n{fmt_task(task, show_freelancer=True)}\n\n"
                f"Submitted by: {esc(user.full_name)}"
            ),
            parse_mode="MarkdownV2",
            reply_markup=review_kb,
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    ctx.user_data.pop("submit_task_id", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  APPROVE
# ═══════════════════════════════════════════════

async def approve_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only\\.", parse_mode="MarkdownV2")
        return

    task_id = int(q.data.split("_")[1])
    task = get_task(task_id)
    if not task:
        await q.message.reply_text("Task not found\\.", parse_mode="MarkdownV2")
        return

    update_task(task_id, status="approved")
    task = get_task(task_id)

    await q.message.reply_text(
        f"✅ *Approved\\!* Payment of €{task['payment']:.2f} marked as sent to {esc(task['freelancer_name'])}\\.",
        parse_mode="MarkdownV2",
    )

    try:
        await ctx.bot.send_message(
            task["freelancer_id"],
            f"🎉 *Your work was approved\\!*\n\n"
            f"Task: _{esc(task['title'])}_\n"
            f"Payment: *€{task['payment']:.2f}* will be sent to you shortly\\.",
            parse_mode="MarkdownV2",
        )
    except Exception:
        pass

    try:
        await ctx.bot.send_message(
            task["client_id"],
            f"✅ Task *{esc(task['title'])}* has been completed and approved\\!",
            parse_mode="MarkdownV2",
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════
#  REJECT CONVERSATION
# ═══════════════════════════════════════════════

async def reject_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    task_id = int(q.data.split("_")[1])
    ctx.user_data["reject_task_id"] = task_id
    await q.message.reply_text(
        f"✏️ Enter the *reason for rejection* for task \\#{task_id}\\:",
        parse_mode="MarkdownV2",
    )
    return ASK_REJECT_REASON


async def receive_reject_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    task_id = ctx.user_data.get("reject_task_id")
    reason = update.message.text.strip()
    task = get_task(task_id)

    if not task:
        await update.message.reply_text("Task not found\\.", parse_mode="MarkdownV2")
        return ConversationHandler.END

    update_task(task_id, status="inprogress", screenshot_id=None, reject_reason=reason)

    await update.message.reply_text(
        f"❌ Task \\#{task_id} rejected\\. Freelancer notified\\.",
        parse_mode="MarkdownV2",
    )

    try:
        await ctx.bot.send_message(
            task["freelancer_id"],
            f"❌ *Submission rejected*\n\n"
            f"Task: _{esc(task['title'])}_\n"
            f"Reason: _{esc(reason)}_\n\n"
            "Please fix the issues and resubmit using My Tasks\\.",
            parse_mode="MarkdownV2",
        )
    except Exception:
        pass

    ctx.user_data.pop("reject_task_id", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  CANCEL
# ═══════════════════════════════════════════════

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text(
        "Operation cancelled\\.",
        parse_mode="MarkdownV2",
        reply_markup=main_menu_keyboard(update.effective_user.id),
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or ADMIN_ID == 0:
        raise RuntimeError("BOT_TOKEN and ADMIN_ID must be set as environment variables.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # ── Conversation: create task (category is now INSIDE) ──
    create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_post, pattern="^menu_post$")],
        states={
            ASK_TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_title)],
            ASK_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_desc)],
            ASK_PAY:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pay)],
            ASK_CATEGORY: [CallbackQueryHandler(ask_category, pattern="^cat_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

    # ── Conversation: submit work ──
    submit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_entry, pattern=r"^submit_\d+$")],
        states={
            ASK_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

    # ── Conversation: reject reason ──
    reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_entry, pattern=r"^reject_\d+$")],
        states={
            ASK_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
        allow_reentry=True,
    )

    # ── Register all handlers ──
    app.add_handler(CommandHandler("start", start))
    app.add_handler(create_conv)
    app.add_handler(submit_conv)
    app.add_handler(reject_conv)

    app.add_handler(CallbackQueryHandler(menu_available,     pattern="^menu_available$"))
    app.add_handler(CallbackQueryHandler(menu_my_freelancer, pattern="^menu_my_freelancer$"))
    app.add_handler(CallbackQueryHandler(menu_my_client,     pattern="^menu_my_client$"))
    app.add_handler(CallbackQueryHandler(menu_review,        pattern="^menu_review$"))
    app.add_handler(CallbackQueryHandler(menu_paid,          pattern="^menu_paid$"))
    app.add_handler(CallbackQueryHandler(take_callback,      pattern=r"^take_\d+$"))
    app.add_handler(CallbackQueryHandler(approve_callback,   pattern=r"^approve_\d+$"))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
