import asyncio
import csv
import os
from datetime import datetime
from binance import AsyncClient, BinanceSocketManager

# --- CONFIG ---
# 10 Volatile Coins for Scalping
SYMBOLS = ['ethusdt', 'dogeusdt', 'ordiusdt', 'tiausdt', 'xrpusdt', 'pepeusdt', 'flokiusdt']

OBI_THRESHOLD = 0.7
TP_PERCENT = 0.005  # 0.5%
SL_PERCENT = 0.003  # 0.3%
CSV_FILE = 'multi_coin_paper_trades.csv'

class MultiCoinOBIBot:
    def __init__(self):
        # Dictionary to track active trades for each symbol
        self.active_trades = {s: None for s in SYMBOLS}
        self.initialize_csv()

    def initialize_csv(self):
        if not os.path.exists(CSV_FILE):
            with open(CSV_FILE, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Time', 'Symbol', 'Side', 'Entry', 'Target', 'Stop', 'Status', 'Exit', 'PNL%'])

    async def log(self, data):
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(data)

    def get_obi(self, depth):
        bids_list = depth.get('b') or depth.get('bids')
        asks_list = depth.get('a') or depth.get('asks')
        
        if not bids_list or not asks_list:
            return 0
        
        bids_vol = sum([float(b[1]) for b in bids_list[:5]])
        asks_vol = sum([float(a[1]) for a in asks_list[:5]])
        
        return (bids_vol - asks_vol) / (bids_vol + asks_vol) if (bids_vol + asks_vol) > 0 else 0

    async def handle_socket_message(self, msg):
        data = msg['data']
        symbol = msg['stream'].split('@')[0]
        obi = self.get_obi(data)
        
        # Fixed: Handle both 'b' and 'bids' for the price extraction
        bids_list = data.get('b') or data.get('bids')
        if not bids_list:
            return
            
        price = float(bids_list[0][0])

        # Trade Management Logic
        if self.active_trades[symbol]:
            t = self.active_trades[symbol]
            is_long = t['side'] == 'LONG'
            
            tp_hit = (is_long and price >= t['target']) or (not is_long and price <= t['target'])
            sl_hit = (is_long and price <= t['stop']) or (not is_long and price >= t['stop'])

            if tp_hit or sl_hit:
                status = 'TP_HIT' if tp_hit else 'SL_HIT'
                pnl = ((price - t['entry']) / t['entry']) * 100 * (1 if is_long else -1)
                await self.log([datetime.now(), symbol.upper(), t['side'], t['entry'], t['target'], t['stop'], status, price, f"{pnl:.2f}"])
                print(f"[{symbol.upper()}] CLOSED: {status} | PNL: {pnl:.2f}%")
                self.active_trades[symbol] = None
        
        # Entry Logic
        elif abs(obi) > OBI_THRESHOLD:
            side = 'LONG' if obi > 0 else 'SHORT'
            target = price * (1 + TP_PERCENT if side == 'LONG' else 1 - TP_PERCENT)
            stop = price * (1 - SL_PERCENT if side == 'LONG' else 1 + SL_PERCENT)
            
            self.active_trades[symbol] = {'side': side, 'entry': price, 'target': target, 'stop': stop}
            await self.log([datetime.now(), symbol.upper(), side, price, target, stop, 'OPEN', '', ''])
            print(f"[{symbol.upper()}] OPENED {side} at {price} (OBI: {obi:.2f})")

    async def run(self):
        print(f"Paper Trading Bot Started. Monitoring: {', '.join(SYMBOLS).upper()}")
        
        while True:
            client = None
            try:
                # Recreate client each retry to avoid stale session/socket state.
                client = await AsyncClient.create(api_key='YOUR_KEY', api_secret='YOUR_SECRET')
                bm = BinanceSocketManager(client)
                
                streams = [f"{s}@depth5@100ms" for s in SYMBOLS]
                ms = bm.multiplex_socket(streams)

                async with ms as tscm:
                    print("Connection established. Streaming data...")
                    while True:
                        res = await tscm.recv()
                        await self.handle_socket_message(res)
            except Exception as e:
                print(f"Connection lost or error occurred: {e}")
                print("Retrying in 10 seconds...")
                
                if client is not None:
                    try:
                        await client.close_connection()
                    except Exception:
                        pass
                
                await asyncio.sleep(10)

if __name__ == '__main__':
    bot = MultiCoinOBIBot()
    asyncio.run(bot.run())