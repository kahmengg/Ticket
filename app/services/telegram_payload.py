"""Turn persisted alert text into small messages with useful actions."""
from urllib.parse import urlsplit


def clip(text, units):
    encoded = text.encode("utf-16-le")
    if len(encoded) <= units * 2:
        return text
    return encoded[:(units - 1) * 2].decode("utf-16-le", errors="ignore") + "…"


def message_payload(chat_id, message):
    lines, buttons = [], []
    for line in message.splitlines():
        label, separator, url = line.partition(": ")
        if separator and url.startswith(("https://", "http://")):
            try:
                valid = bool(urlsplit(url).netloc) and len(url) <= 2048
            except ValueError:
                valid = False
            if valid:
                title = {"URL": "Tickets", "Add concert to calendar": "Concert calendar (~3h)",
                         "Add ticket sale to calendar": "Sale calendar"}.get(label, label.replace(" Discovery Singapore", "").replace(" Singapore", ""))
                if len(buttons) < 8:
                    buttons.append({"text": clip(title, 50), "url": url})
            continue
        lines.append(clip(line, 500))
    # Budget after removing URLs; full ticket links remain usable in the buttons.
    payload = dict(chat_id=chat_id, text=clip("\n".join(lines), 3900) or "Concert update",
                   link_preview_options={"is_disabled": True})
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [buttons[i:i+2] for i in range(0, len(buttons), 2)]}
    return payload
