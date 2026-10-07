from functools import lru_cache
from pymongo import MongoClient
from .config import settings
from .database_indexes import INDEXES, REQUIRED_COLLECTIONS


@lru_cache
def client() -> MongoClient:
    if not settings.mongodb_uri:
        raise RuntimeError("MONGODB_URI is required for live company data")
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=4000)


def db():
    return client()[settings.database_name]


def initialize() -> dict:
    """Create missing collections and indexes without deleting or reseeding data."""
    database = db()
    database.command("ping")
    existing = set(database.list_collection_names())
    created = []
    for name in REQUIRED_COLLECTIONS:
        if name not in existing:
            database.create_collection(name)
            created.append(name)
    indexes_created = []
    for collection_name, specifications in INDEXES.items():
        collection = database[collection_name]
        known = collection.index_information()
        for name, keys, options in specifications:
            if name in known:
                if list(known[name].get("key", [])) != keys:
                    raise RuntimeError(f"Index definition mismatch: {collection_name}.{name}")
                continue
            collection.create_index(keys, name=name, **options)
            indexes_created.append(f"{collection_name}.{name}")
    return {"database": database.name, "collections": list(REQUIRED_COLLECTIONS),
            "collections_created": created, "indexes_created": indexes_created,
            "indexes_total": sum(len(v) for v in INDEXES.values())}
