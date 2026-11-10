from telegram import Update
from telegram.ext import ContextTypes


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Delete messages previously sent by the bot
    message_ids = context.chat_data.get("bot_messages", [])

    for message_id in message_ids:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
        except Exception:
            pass

    # Delete the /clear command itself
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=update.message.message_id,
        )
    except Exception:
        pass

    context.chat_data["bot_messages"] = []