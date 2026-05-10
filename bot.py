import asyncio
from datetime import datetime

from binance import AsyncClient, BinanceSocketManager

from config import (
    CAPITAL_USDT,
    MAX_LOSS_LIMIT,
    MAX_LEVERAGE,
    MAX_PROFIT_LIMIT,
    OBI_THRESHOLD,
    RISK_PER_TRADE_PERCENT,
    SL_PERCENT,
    SYMBOLS,
    TP_PERCENT,
)
from notifier import send_telegram
from storage import initialize_csv, log_trade, archive_and_reset_csv


class MultiCoinOBIBot:
    def __init__(self):
        self.active_trades = {symbol: None for symbol in SYMBOLS}
        self.cumulative_pnl = 0.0
        self.cumulative_pnl_usdt = 0.0
        self.is_running = True
        initialize_csv()

    @staticmethod
    def get_obi(depth):
        bids_list = depth.get("b") or depth.get("bids")
        asks_list = depth.get("a") or depth.get("asks")

        if not bids_list or not asks_list:
            return 0

        bids_vol = sum(float(bid[1]) for bid in bids_list[:5])
        asks_vol = sum(float(ask[1]) for ask in asks_list[:5])
        total = bids_vol + asks_vol
        return (bids_vol - asks_vol) / total if total > 0 else 0

    async def handle_socket_message(self, msg):
        if not self.is_running:
            return

        data = msg["data"]
        symbol = msg["stream"].split("@")[0]
        obi = self.get_obi(data)

        bids_list = data.get("b") or data.get("bids")
        if not bids_list:
            return

        price = float(bids_list[0][0])

        if self.active_trades[symbol]:
            trade = self.active_trades[symbol]
            is_long = trade["side"] == "LONG"

            tp_hit = (is_long and price >= trade["target"]) or (not is_long and price <= trade["target"])
            sl_hit = (is_long and price <= trade["stop"]) or (not is_long and price >= trade["stop"])

            if tp_hit or sl_hit:
                status = "TP_HIT" if tp_hit else "SL_HIT"
                pnl_pct = ((price - trade["entry"]) / trade["entry"]) * 100 * (1 if is_long else -1)
                price_move = ((price - trade["entry"]) / trade["entry"]) * (1 if is_long else -1)
                pnl_usdt = trade["notional_usdt"] * price_move

                self.cumulative_pnl_usdt += pnl_usdt
                self.cumulative_pnl = (self.cumulative_pnl_usdt / CAPITAL_USDT) * 100

                await log_trade(
                    [
                        datetime.now(),
                        symbol.upper(),
                        trade["side"],
                        trade["entry"],
                        trade["target"],
                        trade["stop"],
                        trade["leverage"],
                        trade["qty"],
                        trade["notional_usdt"],
                        trade["risk_usdt"],
                        status,
                        price,
                        f"{pnl_pct:.2f}",
                        f"{pnl_usdt:.2f}",
                    ]
                )
                print(
                    f"[{symbol.upper()}] CLOSED: {status} | PNL: {pnl_pct:.2f}% ({pnl_usdt:.2f} USDT) | "
                    f"Session: {self.cumulative_pnl:.2f}% ({self.cumulative_pnl_usdt:.2f} USDT)"
                )
                self.active_trades[symbol] = None

                if self.cumulative_pnl >= MAX_PROFIT_LIMIT:
                    message = (
                        f"Target reached!\\nSession PNL: {self.cumulative_pnl:.2f}% "
                        f"({self.cumulative_pnl_usdt:.2f} USDT)\\n"
                        "Archiving trades and stopping bot."
                    )
                    print(message)
                    send_telegram(message)
                    await archive_and_reset_csv()
                    self.is_running = False

                elif self.cumulative_pnl <= MAX_LOSS_LIMIT:
                    message = (
                        f"Circuit breaker hit!\\nSession PNL: {self.cumulative_pnl:.2f}% "
                        f"({self.cumulative_pnl_usdt:.2f} USDT)\\n"
                        "Archiving trades and stopping bot."
                    )
                    print(message)
                    send_telegram(message)
                    await archive_and_reset_csv()
                    self.is_running = False

        elif abs(obi) > OBI_THRESHOLD and self.is_running:
            side = "LONG" if obi > 0 else "SHORT"
            target = price * (1 + TP_PERCENT if side == "LONG" else 1 - TP_PERCENT)
            stop = price * (1 - SL_PERCENT if side == "LONG" else 1 + SL_PERCENT)

            risk_usdt = CAPITAL_USDT * (RISK_PER_TRADE_PERCENT / 100)
            notional_usdt = risk_usdt / SL_PERCENT if SL_PERCENT > 0 else CAPITAL_USDT
            raw_leverage = notional_usdt / CAPITAL_USDT if CAPITAL_USDT > 0 else 1
            leverage = max(1.0, min(raw_leverage, float(MAX_LEVERAGE)))
            notional_usdt = CAPITAL_USDT * leverage
            qty = notional_usdt / price if price > 0 else 0

            self.active_trades[symbol] = {
                "side": side,
                "entry": price,
                "target": target,
                "stop": stop,
                "leverage": round(leverage, 2),
                "qty": round(qty, 6),
                "notional_usdt": round(notional_usdt, 2),
                "risk_usdt": round(notional_usdt * SL_PERCENT, 2),
            }
            await log_trade(
                [
                    datetime.now(),
                    symbol.upper(),
                    side,
                    price,
                    target,
                    stop,
                    self.active_trades[symbol]["leverage"],
                    self.active_trades[symbol]["qty"],
                    self.active_trades[symbol]["notional_usdt"],
                    self.active_trades[symbol]["risk_usdt"],
                    "OPEN",
                    "",
                    "",
                    "",
                ]
            )
            print(
                f"[{symbol.upper()}] OPENED {side} (OBI: {obi:.2f}) | Price: {price} | "
                f"Lev: {self.active_trades[symbol]['leverage']}x | "
                f"Risk: {self.active_trades[symbol]['risk_usdt']:.2f} USDT"
            )

    async def run(self):
        print(f"Bot Started. Goal: +{MAX_PROFIT_LIMIT}% | Stop: {MAX_LOSS_LIMIT}%")

        while self.is_running:
            client = None
            try:
                client = await AsyncClient.create(api_key="YOUR_KEY", api_secret="YOUR_SECRET")
                socket_manager = BinanceSocketManager(client)
                streams = [f"{symbol}@depth5@100ms" for symbol in SYMBOLS]
                socket = socket_manager.multiplex_socket(streams)

                async with socket as stream:
                    print("Connection active...")
                    while self.is_running:
                        result = await stream.recv()
                        await self.handle_socket_message(result)
            except Exception as e:
                if self.is_running:
                    print(f"Connection lost: {e}. Retrying in 10s...")
                    if client:
                        await client.close_connection()
                    await asyncio.sleep(10)
                else:
                    break

        if client:
            await client.close_connection()
        print("Bot fully shut down.")
