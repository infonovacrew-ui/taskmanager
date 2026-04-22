"""
Freelance Task Bot — Telegram
Plain text mode — no MarkdownV2 formatting issues
"""

import os
import logging
import sqlite3
from datetime import datetime, timezone
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

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
DB_PATH   = os.environ.get("DB_PATH", "tasks.db")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ASK_TITLE, ASK_DESC, ASK_PAY, ASK_CATEGORY, ASK_SCREENSHOT, ASK_REJECT_REASON = range(6)

# ═══════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
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
        )
    """)
    con.commit()
    con.close()


def get_db():
    return sqlite3.connect(DB_PATH)


def create_task(client_id, client_name, title, desc, payment, category):
    now = datetime.now(timezone.utc).isoformat()
    con = get_db()
    cur = con.execute(
        "INSERT INTO tasks (client_id,client_name,title,description,payment,category,status,created_at,updated_at) "
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
    row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def list_tasks(status=None, freelancer_id=None, client_id=None):
    con = get_db()
    con.row_factory = sqlite3.Row
    q = "SELECT * FROM tasks WHERE 1=1"
    p = []
    if status:        q += " AND status=?";        p.append(status)
    if freelancer_id is not None: q += " AND freelancer_id=?"; p.append(freelancer_id)
    if client_id is not None:     q += " AND client_id=?";     p.append(client_id)
    rows = con.execute(q + " ORDER BY id DESC", p).fetchall()
    con.close()
    return [dict(r) for r in rows]


def update_task(task_id, **kw):
    kw["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k}=?" for k in kw)
    con = get_db()
    con.execute(f"UPDATE tasks SET {sets} WHERE id=?", list(kw.values()) + [task_id])
    con.commit()
    con.close()


# ═══════════════════════════════════════════════
#  HELPERS  (plain text — zero escaping needed)
# ═══════════════════════════════════════════════

STATUS = {
    "available":  "🟢 Available",
    "inprogress": "🔵 In Progress",
    "review":     "🟡 Under Review",
    "approved":   "✅ Approved",
    "rejected":   "❌ Rejected",
}

CAT_ICON = {"writing":"✍️","design":"🎨","research":"🔬","data":"📊","other":"📦"}


def fmt(t, show_fl=False):
    lines = [
        f"{CAT_ICON.get(t['category'],'📦')} {t['title']}",
        f"📋 {t['description']}",
        f"💶 Payment: €{t['payment']:.2f}",
        f"📂 Category: {t['category'].capitalize()}",
        f"🏷 Status: {STATUS.get(t['status'], t['status'])}",
        f"🆔 Task #{t['id']}",
    ]
    if show_fl and t.get("freelancer_name"):
        lines.append(f"👤 Claimed by: {t['freelancer_name']}")
    if t.get("reject_reason"):
        lines.append(f"⛔ Rejection: {t['reject_reason']}")
    return "\n".join(lines)


def menu_kb(user_id):
    kb = [
        [InlineKeyboardButton("➕ Post a Task",              callback_data="menu_post")],
        [InlineKeyboardButton("📋 Available Tasks",          callback_data="menu_available")],
        [InlineKeyboardButton("🗂 My Tasks (Freelancer)",    callback_data="menu_my_freelancer")],
        [InlineKeyboardButton("📁 My Posted Tasks (Client)", callback_data="menu_my_client")],
    ]
    if user_id == ADMIN_ID:
        kb += [
            [InlineKeyboardButton("🔔 Review Queue",    callback_data="menu_review")],
            [InlineKeyboardButton("💰 Approved & Paid", callback_data="menu_paid")],
        ]
    return InlineKeyboardMarkup(kb)


def cat_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Writing",  callback_data="cat_writing"),
         InlineKeyboardButton("🎨 Design",   callback_data="cat_design")],
        [InlineKeyboardButton("🔬 Research", callback_data="cat_research"),
         InlineKeyboardButton("📊 Data",     callback_data="cat_data")],
        [InlineKeyboardButton("📦 Other",    callback_data="cat_other")],
    ])


async def send(update_or_msg, text, kb=None):
    """Send plain text — works from both Message and CallbackQuery."""
    msg = update_or_msg if hasattr(update_or_msg, "reply_text") else update_or_msg.message
    await msg.reply_text(text, reply_markup=kb)


# ═══════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n"
        "This is the Freelance Task Bot. Here you can:\n"
        "• Post tasks as a Client\n"
        "• Claim and complete tasks as a Freelancer\n"
        "• Get paid once your work is approved\n\n"
        "Choose an option below:",
        reply_markup=menu_kb(user.id),
    )


# ═══════════════════════════════════════════════
#  MENU HANDLERS
# ═══════════════════════════════════════════════

async def menu_available(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    tasks = list_tasks(status="available")
    if not tasks:
        await q.message.reply_text("😴 No available tasks right now. Check back later!")
        return
    for t in tasks:
        await q.message.reply_text(
            fmt(t),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"🙋 Take this task  •  €{t['payment']:.2f}", callback_data=f"take_{t['id']}")
            ]])
        )


async def menu_my_freelancer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    tasks = list_tasks(freelancer_id=q.from_user.id)
    if not tasks:
        await q.message.reply_text("You haven't claimed any tasks yet.")
        return
    for t in tasks:
        kb = None
        if t["status"] == "inprogress":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📤 Submit completed work", callback_data=f"submit_{t['id']}")]])
        await q.message.reply_text(fmt(t), reply_markup=kb)


async def menu_my_client(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    tasks = list_tasks(client_id=q.from_user.id)
    if not tasks:
        await q.message.reply_text("You haven't posted any tasks yet.")
        return
    for t in tasks:
        await q.message.reply_text(fmt(t, show_fl=True))


async def menu_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only."); return
    tasks = list_tasks(status="review")
    if not tasks:
        await q.message.reply_text("✅ No pending submissions."); return
    for t in tasks:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve & Pay", callback_data=f"approve_{t['id']}"),
            InlineKeyboardButton("❌ Reject",         callback_data=f"reject_{t['id']}"),
        ]])
        if t.get("screenshot_id"):
            await q.message.reply_photo(photo=t["screenshot_id"], caption=fmt(t, show_fl=True), reply_markup=kb)
        else:
            await q.message.reply_text(fmt(t, show_fl=True), reply_markup=kb)


async def menu_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only."); return
    tasks = list_tasks(status="approved")
    if not tasks:
        await q.message.reply_text("No approved tasks yet."); return
    lines = ["💰 Approved & Paid Tasks\n"]
    for t in tasks:
        lines.append(f"#{t['id']} — {t['title']} — €{t['payment']:.2f} → {t.get('freelancer_name','?')}")
    await q.message.reply_text("\n".join(lines))


# ═══════════════════════════════════════════════
#  CREATE TASK CONVERSATION
# ═══════════════════════════════════════════════

async def menu_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["nt"] = {}
    await q.message.reply_text("📝 Create a new task\n\nStep 1 of 4 — What is the title of this task?")
    return ASK_TITLE


async def ask_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["nt"]["title"] = update.message.text.strip()
    await update.message.reply_text("Step 2 of 4 — Write a description of what needs to be done:")
    return ASK_DESC


async def ask_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["nt"]["desc"] = update.message.text.strip()
    await update.message.reply_text("Step 3 of 4 — What is the payment amount in € (numbers only, e.g. 25)?")
    return ASK_PAY


async def ask_pay(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        pay = float(update.message.text.strip().replace(",", "."))
        if pay <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a valid positive number (e.g. 25).")
        return ASK_PAY
    ctx.user_data["nt"]["payment"] = pay
    await update.message.reply_text("Step 4 of 4 — Pick a category:", reply_markup=cat_kb())
    return ASK_CATEGORY


async def ask_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    category = q.data.replace("cat_", "")
    user = q.from_user
    nt = ctx.user_data.get("nt", {})

    if not nt or "title" not in nt:
        await q.message.reply_text("⚠️ Something went wrong. Please use /start and try again.")
        return ConversationHandler.END

    task_id = create_task(user.id, user.full_name, nt["title"], nt["desc"], nt["payment"], category)
    ctx.user_data.pop("nt", None)
    task = get_task(task_id)

    await q.message.reply_text(
        f"🎉 Task posted successfully!\n\n{fmt(task)}",
        reply_markup=menu_kb(user.id),
    )

    try:
        await ctx.bot.send_message(ADMIN_ID, f"📬 New task posted\n\n{fmt(task)}\n\nPosted by: {user.full_name}")
    except Exception as e:
        logger.warning(f"Could not notify admin: {e}")

    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  TAKE TASK
# ═══════════════════════════════════════════════

async def take_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    task_id = int(q.data.split("_")[1])
    user = q.from_user
    task = get_task(task_id)

    if not task:
        await q.message.reply_text("⚠️ Task not found."); return
    if task["status"] != "available":
        await q.message.reply_text("⛔ This task is no longer available."); return

    update_task(task_id, status="inprogress", freelancer_id=user.id, freelancer_name=user.full_name)
    task = get_task(task_id)

    await q.message.reply_text(
        f"🔵 Task claimed!\n\n{fmt(task)}\n\nComplete the work then press Submit.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📤 Submit completed work", callback_data=f"submit_{task_id}")
        ]])
    )
    try:
        await ctx.bot.send_message(ADMIN_ID, f"🔵 Task #{task_id} claimed by {user.full_name} (ID: {user.id})")
    except Exception: pass
    try:
        await ctx.bot.send_message(task["client_id"], f"🔵 Your task '{task['title']}' was claimed by {user.full_name}!")
    except Exception: pass


# ═══════════════════════════════════════════════
#  SUBMIT WORK CONVERSATION
# ═══════════════════════════════════════════════

async def submit_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    task_id = int(q.data.split("_")[1])
    user = q.from_user
    task = get_task(task_id)

    if not task or task["freelancer_id"] != user.id:
        await q.message.reply_text("⚠️ You don't have access to this task.")
        return ConversationHandler.END
    if task["status"] != "inprogress":
        await q.message.reply_text("⚠️ This task is not in progress.")
        return ConversationHandler.END

    ctx.user_data["submit_task_id"] = task_id
    await q.message.reply_text(f"📸 Send a photo/screenshot of your completed work for task #{task_id}: {task['title']}")
    return ASK_SCREENSHOT


async def receive_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task_id = ctx.user_data.get("submit_task_id")

    if not task_id:
        await update.message.reply_text("⚠️ Session expired. Please use /start and try again.")
        return ConversationHandler.END
    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a photo.")
        return ASK_SCREENSHOT

    photo_id = update.message.photo[-1].file_id
    update_task(task_id, status="review", screenshot_id=photo_id)
    task = get_task(task_id)

    await update.message.reply_text(
        f"✅ Submitted! The admin will review your work for task #{task_id}.\nYou'll be notified once approved or rejected.",
        reply_markup=menu_kb(user.id),
    )

    try:
        await ctx.bot.send_photo(
            ADMIN_ID,
            photo=photo_id,
            caption=f"🔔 Review requested\n\n{fmt(task, show_fl=True)}\n\nSubmitted by: {user.full_name}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve & Pay", callback_data=f"approve_{task_id}"),
                InlineKeyboardButton("❌ Reject",         callback_data=f"reject_{task_id}"),
            ]])
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

    ctx.user_data.pop("submit_task_id", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  APPROVE
# ═══════════════════════════════════════════════

async def approve_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only."); return

    task_id = int(q.data.split("_")[1])
    task = get_task(task_id)
    if not task:
        await q.message.reply_text("Task not found."); return

    update_task(task_id, status="approved")
    task = get_task(task_id)
    await q.message.reply_text(f"✅ Approved! Payment of €{task['payment']:.2f} marked as sent to {task['freelancer_name']}.")

    try:
        await ctx.bot.send_message(
            task["freelancer_id"],
            f"🎉 Your work was approved!\n\nTask: {task['title']}\nPayment: €{task['payment']:.2f} will be sent to you shortly."
        )
    except Exception: pass
    try:
        await ctx.bot.send_message(task["client_id"], f"✅ Task '{task['title']}' has been completed and approved!")
    except Exception: pass


# ═══════════════════════════════════════════════
#  REJECT CONVERSATION
# ═══════════════════════════════════════════════

async def reject_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.message.reply_text("⛔ Admins only.")
        return ConversationHandler.END

    task_id = int(q.data.split("_")[1])
    ctx.user_data["reject_task_id"] = task_id
    await q.message.reply_text(f"✏️ Enter the reason for rejection for task #{task_id}:")
    return ASK_REJECT_REASON


async def receive_reject_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END

    task_id = ctx.user_data.get("reject_task_id")
    reason = update.message.text.strip()
    task = get_task(task_id)

    if not task:
        await update.message.reply_text("Task not found.")
        return ConversationHandler.END

    update_task(task_id, status="inprogress", screenshot_id=None, reject_reason=reason)
    await update.message.reply_text(f"❌ Task #{task_id} rejected. Freelancer notified.")

    try:
        await ctx.bot.send_message(
            task["freelancer_id"],
            f"❌ Submission rejected\n\nTask: {task['title']}\nReason: {reason}\n\nPlease fix the issues and resubmit."
        )
    except Exception: pass

    ctx.user_data.pop("reject_task_id", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  CANCEL
# ═══════════════════════════════════════════════

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("Operation cancelled.", reply_markup=menu_kb(update.effective_user.id))
    return ConversationHandler.END


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or ADMIN_ID == 0:
        raise RuntimeError("Set BOT_TOKEN and ADMIN_ID as environment variables.")

    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    create_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_post, pattern="^menu_post$")],
        states={
            ASK_TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_title)],
            ASK_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_desc)],
            ASK_PAY:      [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pay)],
            ASK_CATEGORY: [CallbackQueryHandler(ask_category, pattern="^cat_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True, allow_reentry=True,
    )

    submit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_entry, pattern=r"^submit_\d+$")],
        states={ASK_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_screenshot)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True, allow_reentry=True,
    )

    reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_entry, pattern=r"^reject_\d+$")],
        states={ASK_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True, allow_reentry=True,
    )

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
