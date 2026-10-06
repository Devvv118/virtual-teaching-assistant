import json
import os
import psycopg
import requests

from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

api_key = os.getenv("AIPIPE_TOKEN")
database_url = os.getenv("DATABASE_URL")

conn = psycopg.connect(database_url)

conn.execute("""
    CREATE EXTENSION IF NOT EXISTS vector;
""")

register_vector(conn)

conn.execute("""
    CREATE TABLE IF NOT EXISTS course_content_book (
        id BIGSERIAL PRIMARY KEY,
        url TEXT NOT NULL,
        content TEXT NOT NULL,
        embedding VECTOR(1536) NOT NULL
    );
""")

conn.commit()


BATCH_SIZE = 5
buffer = []
count = 0


def process_buffer(buffer):
    texts = [item["content"] for item in buffer]

    response = requests.post(
        "https://aipipe.org/openai/v1/embeddings",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json={
            "model": "text-embedding-3-small",
            "input": texts
        }
    )
    response.raise_for_status()
    embeddings = [d["embedding"] for d in response.json()["data"]]

    for i, doc in enumerate(buffer):
        try:
            conn.execute("""
                    INSERT INTO course_content_book (url,content,embedding)
                    VALUES (%s,%s,%s)
                """, (
                    doc["url"],
                    doc["content"],
                    embeddings[i],
                ))

        except Exception as e:
            print(f"Error inserting document: {e}")

    conn.commit()


with open("Jan25-chunked.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        data = json.loads(line)
        url = data.get("url")
        content = data.get("content")

        if not content or not url:
            continue

        buffer.append({
            "url": url,
            "content": content,
        })

        if len(buffer) == BATCH_SIZE:
            process_buffer(buffer)

            count+=BATCH_SIZE
            print(count)

            buffer = []

if buffer:
    process_buffer(buffer)

    count+=len(buffer)
    print(count)

conn.close()