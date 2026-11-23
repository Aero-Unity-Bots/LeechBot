from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

client = AsyncIOMotorClient(Config.MONGO_URI)
db = client[Config.DB_NAME]

users_col = db["users"]
fsub_col = db["fsub_channels"]

async def add_user(user_id: int, first_name: str):
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"first_name": first_name, "started_pm": True}},
        upsert=True
    )

async def has_started_bot(user_id: int) -> bool:
    doc = await users_col.find_one({"_id": user_id, "started_pm": True})
    return bool(doc)

async def total_users_count() -> int:
    return await users_col.count_documents({})

async def add_fsub_channel(channel_id: int):
    await fsub_col.update_one(
        {"_id": channel_id},
        {"$set": {"_id": channel_id}},
        upsert=True
    )

async def remove_fsub_channel(channel_id: int):
    await fsub_col.delete_one({"_id": channel_id})

async def get_fsub_channels() -> list[int]:
    cursor = fsub_col.find({})
    return [doc["_id"] async for doc in cursor]
