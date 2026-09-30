from pymongo import MongoClient, ASCENDING
from datetime import datetime, timezone
from bson import ObjectId

from .config import MONGO_URI, DB_NAME

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]

files   = db.files
links   = db.links
users   = db.users
clones  = db.clones
bans    = db.bans
batches = db.batches

files.create_index([("short_id", ASCENDING)], unique=True)
files.create_index([("owner_id", ASCENDING)])
files.create_index([("created", ASCENDING)], expireAfterSeconds=60*60*24*365)

links.create_index([("token", ASCENDING)], unique=True)
links.create_index([("owner_id", ASCENDING)])
links.create_index([("created", ASCENDING)], expireAfterSeconds=60*60*24*365)

users.create_index([("user_id", ASCENDING)], unique=True)
clones.create_index([("owner_id", ASCENDING)])
bans.create_index([("user_id", ASCENDING)], unique=True)

batches.create_index([("token", ASCENDING)], unique=True, sparse=True)
batches.create_index([("owner_id", ASCENDING)])
batches.create_index([("state", ASCENDING)])
batches.create_index([("created", ASCENDING)], expireAfterSeconds=60*60*24*365)


def get_user(user_id):
    return users.find_one({"user_id": user_id})


def upsert_user(user_id, username=None, first_name=None):
    return users.update_one(
        {"user_id": user_id},
        {"$set": {"username": username, "first_name": first_name,
                  "last_seen": datetime.now(timezone.utc)},
         "$setOnInsert": {"joined": datetime.now(timezone.utc)}},
        upsert=True,
    )


def count_users():
    return users.count_documents({})


def save_file(short_id, owner_id, file_id, message_id, name, size, mime):
    files.insert_one({
        "short_id": short_id, "owner_id": owner_id,
        "file_id": file_id, "message_id": message_id,
        "name": name, "size": size, "mime": mime,
        "created": datetime.now(timezone.utc), "views": 0,
    })


def get_file(short_id):
    return files.find_one({"short_id": short_id})


def inc_views(short_id):
    files.update_one({"short_id": short_id}, {"$inc": {"views": 1}})


def user_files(owner_id, limit=20):
    return list(files.find({"owner_id": owner_id}).sort("created", -1).limit(limit))


def count_files():
    return files.count_documents({})


def save_link(token, owner_id, file_id, message_id, kind,
              preview_text=None, name=None):
    links.insert_one({
        "token": token, "owner_id": owner_id,
        "file_id": file_id, "message_id": message_id,
        "kind": kind, "preview_text": preview_text, "name": name,
        "created": datetime.now(timezone.utc), "views": 0,
    })


def get_link(token):
    return links.find_one({"token": token})


def inc_link_views(token):
    links.update_one({"token": token}, {"$inc": {"views": 1}})


def user_links(owner_id, limit=20):
    return list(links.find({"owner_id": owner_id}).sort("created", -1).limit(limit))


def count_links():
    return links.count_documents({})


def create_batch(owner_id):
    r = batches.insert_one({
        "owner_id": owner_id, "messages": [],
        "token": None, "state": "collecting",
        "created": datetime.now(timezone.utc), "views": 0,
    })
    return r.inserted_id


def get_active_batch(owner_id):
    return batches.find_one(
        {"owner_id": owner_id, "state": {"$in": ["collecting", "paused"]}},
        sort=[("created", -1)],
    )


def get_batch_by_id(bid):
    try:
        return batches.find_one({"_id": ObjectId(bid)})
    except Exception:
        return None


def get_batch_by_token(token):
    return batches.find_one({"token": token})


def add_batch_message(bid, message_id, kind, preview=None):
    batches.update_one(
        {"_id": ObjectId(bid)},
        {"$push": {"messages": {
            "message_id": message_id, "kind": kind, "preview": preview,
        }}},
    )


def set_batch_state(bid, state):
    batches.update_one({"_id": ObjectId(bid)}, {"$set": {"state": state}})


def set_batch_token(bid, token):
    batches.update_one(
        {"_id": ObjectId(bid)},
        {"$set": {"token": token, "state": "done"}},
    )


def inc_batch_views(token):
    batches.update_one({"token": token}, {"$inc": {"views": 1}})


def user_batches(owner_id, limit=20):
    return list(batches.find({
        "owner_id": owner_id, "state": "done",
    }).sort("created", -1).limit(limit))


def ban_user(user_id, reason=None):
    bans.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "reason": reason,
                  "banned_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


def unban_user(user_id):
    r = bans.delete_one({"user_id": user_id})
    return r.deleted_count > 0


def is_banned(user_id):
    return bans.find_one({"user_id": user_id}) is not None


def count_bans():
    return bans.count_documents({})


def all_user_ids():
    banned = {b["user_id"] for b in bans.find({}, {"user_id": 1})}
    for u in users.find({}, {"user_id": 1}):
        if u["user_id"] not in banned:
            yield u["user_id"]


def register_clone(owner_id, bot_token, bot_username, cookies=None):
    clones.insert_one({
        "owner_id": owner_id, "bot_token": bot_token,
        "bot_username": bot_username, "cookies": cookies,
        "active": True, "created": datetime.now(timezone.utc),
    })


def get_clones(owner_id):
    return list(clones.find({"owner_id": owner_id, "active": True}))