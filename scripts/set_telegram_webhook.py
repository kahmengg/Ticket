import os
import sys

import requests


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    public_base_url = os.getenv("PUBLIC_BASE_URL")
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")

    if not token or not public_base_url:
        print("Set TELEGRAM_BOT_TOKEN and PUBLIC_BASE_URL first.")
        return 1

    webhook_url = public_base_url.rstrip("/") + "/telegram/webhook"
    payload = {"url": webhook_url}
    if secret:
        payload["secret_token"] = secret

    response = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json=payload,
        timeout=15,
    )
    print(response.status_code)
    print(response.text)
    response.raise_for_status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
