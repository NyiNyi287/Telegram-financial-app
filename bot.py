import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ConversationHandler, ContextTypes
)

# States for send/transfer
GET_USERNAME, GET_AMOUNT = range(2)

# Database connection
conn = sqlite3.connect('users.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, balance REAL DEFAULT 0)')
c.execute('''CREATE TABLE IF NOT EXISTS history (
    sender TEXT,
    recipient TEXT,
    amount REAL,
    timestamp TEXT
)''')
conn.commit()

# DB helpers
def get_balance(username):
    c.execute('INSERT OR IGNORE INTO users (username) VALUES (?)', (username,))
    conn.commit()
    c.execute('SELECT balance FROM users WHERE username=?', (username,))
    return c.fetchone()[0]

def update_balance(username, amount):
    get_balance(username)
    c.execute('UPDATE users SET balance = balance + ? WHERE username=?', (amount, username))
    conn.commit()

def log_transaction(sender, recipient, amount):
    timestamp = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
    c.execute('INSERT INTO history (sender, recipient, amount, timestamp) VALUES (?, ?, ?, ?)',
              (sender, recipient, amount, timestamp))
    conn.commit()

# Bot commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /balance, /deposit, /send, or /history.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_obj = update.effective_user
    name = f"{user_obj.first_name} {user_obj.last_name or ''}".strip()
    username = user_obj.username or str(user_obj.id)
    bal = get_balance(username)
    await update.message.reply_text(f"{name}, your balance is {bal:.2f}")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.username or str(update.effective_user.id)
    try:
        amount = float(context.args[0])
        if amount <= 0:
            raise ValueError
        update_balance(user, amount)
        await update.message.reply_text(f"Deposited {amount:.2f}. New balance: {get_balance(user):.2f}")
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /deposit <amount> (positive number)")

async def send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Enter recipient username:")
    return GET_USERNAME

async def get_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["recipient"] = update.message.text.strip().lstrip('@')
    await update.message.reply_text("Enter amount to send:")
    return GET_AMOUNT

async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_obj = update.effective_user
    sender = sender_obj.username or str(sender_obj.id)
    recipient = context.user_data["recipient"]
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        if get_balance(sender) < amount:
            await update.message.reply_text("Insufficient balance.")
        else:
            update_balance(sender, -amount)
            update_balance(recipient, amount)
            log_transaction(sender, recipient, amount)
            await update.message.reply_text(f"Sent {amount:.2f} to @{recipient}")
    except ValueError:
        await update.message.reply_text("Invalid amount.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Transaction cancelled.")
    return ConversationHandler.END

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_obj = update.effective_user
    user = user_obj.username or str(user_obj.id)
    c.execute('SELECT sender, recipient, amount, timestamp FROM history WHERE sender=? OR recipient=? ORDER BY rowid DESC LIMIT 5', (user, user))
    rows = c.fetchall()

    if rows:
        msg = ""
        for s, r, a, t in rows:
            s_display = "You" if s == user else f"@{s}"
            r_display = "You" if r == user else f"@{r}"
            msg += f"{s_display} -> {r_display}: {a:.2f} on {t}\n"
    else:
        msg = "No transactions found."
    await update.message.reply_text(msg)

# Main
def main():
    app = ApplicationBuilder().token("7734594664:AAF8s9aIPZdQFRsahCD14uGIaN-g8SzRhr0").build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("send", send), CommandHandler("transfer", send)],
        states={
            GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_recipient)],
            GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(conv)

    app.run_polling()

if __name__ == "__main__":
    main()
