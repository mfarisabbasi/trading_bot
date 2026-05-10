import csv
import os
import shutil
from datetime import datetime

from config import CSV_FILE


CSV_HEADERS = [
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


def _migrate_if_needed():
    with open(CSV_FILE, "r", newline="") as file_obj:
        rows = list(csv.reader(file_obj))

    if not rows:
        with open(CSV_FILE, "w", newline="") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(CSV_HEADERS)
        return

    existing_header = rows[0]
    if existing_header == CSV_HEADERS:
        return

    header_index = {name: idx for idx, name in enumerate(existing_header)}
    migrated = [CSV_HEADERS]

    for row in rows[1:]:
        new_row = [""] * len(CSV_HEADERS)
        for i, col in enumerate(CSV_HEADERS):
            if col in header_index and header_index[col] < len(row):
                new_row[i] = row[header_index[col]]
        migrated.append(new_row)

    with open(CSV_FILE, "w", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerows(migrated)


def initialize_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerow(CSV_HEADERS)
        return

    _migrate_if_needed()


async def log_trade(data):
    with open(CSV_FILE, "a", newline="") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerow(data)


async def archive_and_reset_csv():
    """Archive current CSV with timestamp to data folder, reset for next session."""
    if not os.path.exists(CSV_FILE):
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived_name = f"multi_coin_paper_trades_{timestamp}.csv"
    archived_path = os.path.join("data", archived_name)
    
    shutil.move(CSV_FILE, archived_path)
    
    initialize_csv()
