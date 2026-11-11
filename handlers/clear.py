from telegram import Update
from telegram.ext import ContextTypes


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Messages tracked for cleanup
    message_ids = set(
        context.chat_data.get("bot_messages", [])
    )

    # User messages that contained download URLs
    message_ids.update(
        context.chat_data.get("user_messages", [])
    )

    # Delete everything we have tracked
    for message_id in message_ids:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
        except Exception:
            pass

    # Delete the /clear command itself
    if update.message:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=update.message.message_id,
            )
        except Exception:
            pass

    # Reset tracking
    context.chat_data["bot_messages"] = []
    context.chat_data["user_messages"] = []