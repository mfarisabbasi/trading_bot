import os


SYMBOLS = ["ethusdt", "dogeusdt", "ordiusdt", "xrpusdt", "pepeusdt", "flokiusdt"]

OBI_THRESHOLD = 0.7
TP_PERCENT = 0.005  # 0.5%
SL_PERCENT = 0.003  # 0.3%

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb+srv://farisabbasi:farisabbasi@cluster0.ta7d6pv.mongodb.net/?retryWrites=true&w=majority&appName=trading-bot")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "obi_trading_bot")
MONGODB_TRADES_COLLECTION = os.getenv("MONGODB_TRADES_COLLECTION", "trades")
MONGODB_SESSIONS_COLLECTION = os.getenv("MONGODB_SESSIONS_COLLECTION", "sessions")

CAPITAL_USDT = 360.0
RISK_PER_TRADE_PERCENT = 1.0
MAX_LEVERAGE = 20

MAX_PROFIT_LIMIT = 5.0  # Stop at +5% Total PNL
MAX_LOSS_LIMIT = -5.0   # Stop at -5% Total PNL

TELEGRAM_TOKEN = "8796820260:AAEp-waKBcFfOjUZ7CUwdh8nzk7nf-DePzQ"
TELEGRAM_CHAT_ID = "8060459742"
