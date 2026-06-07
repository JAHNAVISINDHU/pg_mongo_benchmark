"""Shared DB connection helpers."""
import os
import psycopg2
from pymongo import MongoClient


def pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        dbname=os.getenv("POSTGRES_DB", "activity_db"),
    )


def mongo_db():
    host = os.getenv("MONGO_HOST", "localhost")
    port = int(os.getenv("MONGO_PORT", 27017))
    user = os.getenv("MONGO_USER", "mongo")
    pwd  = os.getenv("MONGO_PASSWORD", "mongo")
    db   = os.getenv("MONGO_DB", "activity_db")
    uri  = f"mongodb://{user}:{pwd}@{host}:{port}/{db}?authSource=admin"
    client = MongoClient(uri)
    return client[db]
