from datetime import datetime
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient

from config import (
    CAPITAL_USDT,
    MONGODB_DATABASE,
    MONGODB_SESSIONS_COLLECTION,
    MONGODB_TRADES_COLLECTION,
    MONGODB_URI,
)


TRADE_FIELDS = [
    "Time",
    "Symbol",
    "Side",
    "Entry",
    "Target",
    "Stop",
    "Leverage",
    "Qty",
    "NotionalUSDT",
    "RiskUSDT",
    "Status",
    "Exit",
    "PNL%",
    "PNL_USDT",
]

_client = None
_database = None
_trades = None
_sessions = None
_current_session_id = None


def _validate_uri():
    if "<username>" in MONGODB_URI or "<password>" in MONGODB_URI or "<cluster-url>" in MONGODB_URI:
        raise ValueError("Set MONGODB_URI env var or update config.py with your MongoDB Atlas connection string.")


def _connect():
    global _client, _database, _trades, _sessions

    if _trades is not None and _sessions is not None:
        return

    _validate_uri()
    _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    _client.admin.command("ping")
    _database = _client[MONGODB_DATABASE]
    _trades = _database[MONGODB_TRADES_COLLECTION]
    _sessions = _database[MONGODB_SESSIONS_COLLECTION]

    _trades.create_index([("session_id", ASCENDING), ("Time", DESCENDING)])
    _trades.create_index([("Symbol", ASCENDING), ("Time", DESCENDING)])
    _sessions.create_index([("started_at", DESCENDING)])


def _latest_known_capital():
    latest_session = _sessions.find_one(
        {"ending_capital": {"$exists": True}},
        sort=[("ended_at", DESCENDING), ("started_at", DESCENDING)],
    )
    if latest_session and latest_session.get("ending_capital") is not None:
        return float(latest_session["ending_capital"])
    return float(CAPITAL_USDT)


def _start_new_session(starting_capital=None):
    global _current_session_id

    if starting_capital is None:
        starting_capital = _latest_known_capital()

    starting_capital = round(float(starting_capital), 2)
    _current_session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    _sessions.insert_one(
        {
            "session_id": _current_session_id,
            "started_at": datetime.utcnow(),
            "ended_at": None,
            "status": "ACTIVE",
            "starting_capital": starting_capital,
            "ending_capital": None,
        }
    )
    return _current_session_id


def _ensure_active_session():
    global _current_session_id

    _connect()
    if _current_session_id:
        return _current_session_id

    active_session = _sessions.find_one({"status": "ACTIVE"}, sort=[("started_at", DESCENDING)])
    if active_session:
        _current_session_id = active_session["session_id"]
        return _current_session_id

    return _start_new_session()


def initialize_storage():
    session = get_active_session()
    return float(session.get("starting_capital", CAPITAL_USDT))


def get_active_session():
    session_id = _ensure_active_session()
    session = _sessions.find_one({"session_id": session_id}, {"_id": 0})
    if session is None:
        raise ValueError(f"Active session not found for session_id={session_id}")

    update_fields = {}
    if session.get("starting_capital") is None:
        update_fields["starting_capital"] = _latest_known_capital()
    if "ending_capital" not in session:
        update_fields["ending_capital"] = None

    if update_fields:
        _sessions.update_one({"session_id": session_id}, {"$set": update_fields})
        session.update(update_fields)

    return session


def _trade_document(data):
    trade = dict(zip(TRADE_FIELDS, data))
    trade.setdefault("Time", datetime.utcnow())
    trade["session_id"] = _ensure_active_session()
    trade["created_at"] = datetime.utcnow()
    return trade


async def log_trade(data):
    _ensure_active_session()
    _trades.insert_one(_trade_document(data))


async def archive_and_reset_storage(session_pnl_usdt):
    global _current_session_id

    session = get_active_session()
    session_id = session["session_id"]
    starting_capital = float(session.get("starting_capital", CAPITAL_USDT))
    ending_capital = round(starting_capital + float(session_pnl_usdt), 2)

    _sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "ended_at": datetime.utcnow(),
                "status": "ARCHIVED",
                "session_pnl_usdt": round(float(session_pnl_usdt), 2),
                "ending_capital": ending_capital,
            }
        },
    )
    _current_session_id = None
    _start_new_session(ending_capital)
    return ending_capital


def get_session_summaries():
    _connect()
    sessions = list(_sessions.find().sort("started_at", DESCENDING))
    trade_counts = {
        item["_id"]: item["count"]
        for item in _trades.aggregate(
            [
                {"$group": {"_id": "$session_id", "count": {"$sum": 1}}},
            ]
        )
    }

    results = []
    for session in sessions:
        results.append(
            {
                "session_id": session["session_id"],
                "started_at": session.get("started_at"),
                "ended_at": session.get("ended_at"),
                "status": session.get("status", "UNKNOWN"),
                "trade_count": trade_counts.get(session["session_id"], 0),
                "starting_capital": float(session.get("starting_capital", CAPITAL_USDT)),
                "ending_capital": session.get("ending_capital"),
                "session_pnl_usdt": float(session.get("session_pnl_usdt", 0.0) or 0.0),
            }
        )
    return results


def get_trades_for_session(session_id):
    _connect()
    trades = list(
        _trades.find({"session_id": session_id}, {"_id": 0, "created_at": 0, "session_id": 0}).sort("Time", ASCENDING)
    )
    return trades
