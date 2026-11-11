from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import TOKEN
from handlers.download import download
from handlers.clear import clear
from handlers.start import start

def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(4)
        .connection_pool_size(8)
        .pool_timeout(60)
        .build()
    )

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, download)
    )
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("start", start))

    print("Telegram media bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()