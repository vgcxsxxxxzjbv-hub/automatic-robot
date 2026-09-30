import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN       = os.environ["BOT_TOKEN"]
BOT_USERNAME    = os.environ.get("BOT_USERNAME", "")
MONGO_URI       = os.environ["MONGO_URI"]
DB_NAME         = os.environ.get("DB_NAME", "filestore")
STORAGE_CHANNEL = int(os.environ["STORAGE_CHANNEL"])
ADMIN_IDS       = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}

WEBHOOK_URL     = os.environ["WEBHOOK_URL"]
WEBHOOK_SECRET  = os.environ["WEBHOOK_SECRET"]
BASE_URL        = os.environ["BASE_URL"]

START_PHOTO     = os.environ.get("START_PHOTO", "").strip()

_raw_fs = os.environ.get("FORCE_SUB_CHANNELS", "").split(",")
FORCE_SUB_CHANNELS = []
for x in _raw_fs:
    x = x.strip()
    if not x:
        continue
    if x.lstrip("-").isdigit():
        FORCE_SUB_CHANNELS.append(int(x))
    else:
        FORCE_SUB_CHANNELS.append(x.lstrip("@"))

FORCE_SUB_USERNAMES = [
    x.strip().lstrip("@")
    for x in os.environ.get("FORCE_SUB_USERNAMES", "").split(",")
    if x.strip()
]

OWNER_LINK      = os.environ.get("OWNER_LINK", "https://t.me/")
UPDATES_LINK    = os.environ.get("UPDATES_LINK", "https://t.me/")
SUPPORT_LINK    = os.environ.get("SUPPORT_LINK", "https://t.me/")
VERSION         = os.environ.get("VERSION", "1.0.0")