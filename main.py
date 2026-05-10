import asyncio

from bot import MultiCoinOBIBot
from notifier import send_telegram


def main():
    while True:
        bot = MultiCoinOBIBot()
        send_telegram("Bot Started")
        asyncio.run(bot.run())
        send_telegram("Session ended. Restarting bot...")


if __name__ == "__main__":
    main()
