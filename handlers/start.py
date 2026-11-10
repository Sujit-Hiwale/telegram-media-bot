from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\n"
        "Send me any image or video link and I'll download it for you.\n\n"
        "📸 Instagram\n"
        "🎬 YouTube\n"
        "📱 Facebook\n"
        "🌐 Other websites\n\n"
        "Just paste the link here."
    )