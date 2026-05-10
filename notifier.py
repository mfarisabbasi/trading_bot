import os
import time

import requests

from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN


def send_telegram(message):
    """Send Telegram alert with retry + optional proxy fallback."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}

    http_proxy = os.getenv("TELEGRAM_HTTP_PROXY") or os.getenv("HTTP_PROXY")
    https_proxy = os.getenv("TELEGRAM_HTTPS_PROXY") or os.getenv("HTTPS_PROXY")

    proxy_config = None
    if http_proxy or https_proxy:
        proxy_config = {
            "http": http_proxy or https_proxy,
            "https": https_proxy or http_proxy,
        }

    attempts = [None]
    if proxy_config:
        attempts.append(proxy_config)

    for proxies in attempts:
        for attempt in range(1, 4):
            try:
                resp = requests.post(url, json=payload, timeout=15, proxies=proxies)
                resp.raise_for_status()
                print("Telegram notification sent!")
                return True
            except requests.exceptions.RequestException as e:
                mode = "proxy" if proxies else "direct"
                print(f"Telegram send failed ({mode}, try {attempt}/3): {e}")
                if attempt < 3:
                    time.sleep(1.5)

    print("Telegram notification failed after all retries.")
    print("Tip: set TELEGRAM_HTTP_PROXY / TELEGRAM_HTTPS_PROXY or enable Cloudflare WARP.")
    return False
