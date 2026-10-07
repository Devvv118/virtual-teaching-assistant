import os
import re
import sys
import json
import time
import uuid
import httpx
import base64
import psycopg
import filetype
import requests
import uvicorn
import traceback

from datetime import date
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from pgvector import Vector
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List, Optional
from fastapi import HTTPException
from pgvector.psycopg import register_vector
from fastapi.middleware.cors import CORSMiddleware

START_TIME = time.time()
BOOT_LOG = []   # replayed by the frontend terminal via GET /boot

def boot(msg: str, level: str = "info"):
    # Print to the server console AND remember it for the frontend terminal.
    BOOT_LOG.append({"t": round(time.time() - START_TIME, 3), "level": level, "msg": msg})
    print(f"[boot {time.strftime('%H:%M:%S')}] {msg}", flush=True)

boot(f"virtual-teaching-assistant starting · python {sys.version.split()[0]}")

load_dotenv()
boot("environment loaded (.env)", "ok")

DAILY_LIMIT = 10
MAX_QUESTION_LENGTH = 20_000
MAX_IMAGE_SIZE = 20 * 1024 * 1024

api_key = os.getenv("AIPIPE_TOKEN")
database_url = os.getenv("DATABASE_URL")

if api_key:
    print(f"[boot {time.strftime('%H:%M:%S')}] AIPIPE_TOKEN found", flush=True)  # console only
else:
    boot("AIPIPE_TOKEN missing - every request will be refused", "warn")

boot("connecting to PostgreSQL ...")
try:
    conn = psycopg.connect(database_url, autocommit=True)
except Exception as e:
    boot(f"database connection failed: {type(e).__name__}", "error")
    raise
boot("connected to database", "ok")

register_vector(conn)
boot("pgvector registered on connection", "ok")

TABLES = {
    "discourse": "discourse_book",
    "course": "course_content_book",
}

for _table in TABLES.values():
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {_table}")
            boot(f"table {_table}: {cur.fetchone()[0]:,} chunks indexed", "ok")
    except Exception as e:
        boot(f"table {_table}: unavailable ({type(e).__name__})", "warn")

app = FastAPI()
boot("FastAPI app created", "ok")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    # "http://localhost:5173",
    "https://virtual-teaching-assistant-pink.vercel.app",
    ],
    allow_methods=["OPTIONS", "POST", "GET"],
    allow_headers=["*"],
)
boot("CORS middleware enabled", "ok")

COURSE_LINK_PREFIX = "https://tds.s-anand.net/#/"
DISCOURSE_LINK_PREFIX = "https://discourse.onlinedegree.iitm.ac.in/t/"

class QueryRequest(BaseModel):
    question: str = Field(..., max_length=MAX_QUESTION_LENGTH)
    image: Optional[str] = None
    link: Optional[str] = None

def validate_image_size(image_base64: str):
    # Approximate decoded size
    size = len(image_base64) * 3 // 4

    if size > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Image is too large. Maximum size is 20 MB."
        )

async def daily_budget_exceeded() -> bool:
    token = os.getenv("AIPIPE_TOKEN")

    if not token:
        return True

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://aipipe.org/usage",
                headers={
                    "Authorization": f"Bearer {token}"
                }
            )

            response.raise_for_status()
            data = response.json()

            today = date.today()
            today = today.isoformat()

            today_cost = next(
                (
                    item["cost"]
                    for item in data.get("usage", [])
                    if item.get("date") == today
                ),
                0.0
            )

            print(f"today_cost: {today_cost}")
            return today_cost >= DAILY_LIMIT

    except Exception as e:
        print(f"Error checking daily budget: {e}")
        return True

def get_embedding(text: str) -> List:
    url = "https://aipipe.org/openai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "text-embedding-3-small",
        "input": text
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    return response.json()['data'][0]['embedding']

def search_postgres_with_vector(embedding: list, k=2) -> list:

    query_vector = Vector(embedding)

    all_hits = []

    # Discourse
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url, parent_url, content, embedding <=> %s AS distance
                FROM discourse_book
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                 (query_vector, query_vector, k)
            )

            for url, parent_url, content, distance in cur.fetchall():
                all_hits.append({
                    "url": url,
                    "parent_url": parent_url,
                    "content": content,
                    "similarity": 1 - distance
                })

    except Exception as e:
        print(f"PostgreSQL error in discourse_book:")
        print(e)

    # Course content
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url, content, embedding <=> %s AS distance 
                FROM course_content_book
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                 (query_vector, query_vector, k)
            )

            for url, content, distance in cur.fetchall():
                all_hits.append({
                    "url": url,
                    "parent_url": None,
                    "content": content,
                    "similarity": 1 - distance
                })

    except Exception as e:
        print(f"PostgreSQL error in course_content_book:")
        print(e)

    all_hits.sort(
        key=lambda x: x["similarity"],
        reverse=True
    )

    return all_hits[:k]

def search_postgres_with_link(link: str, query_embedding: list) -> list:

    query_vector = Vector(query_embedding)

    if link.startswith("https://tds.s-anand.net/#/"):
        table = TABLES["course"]

        query = f"""
            SELECT url, parent_url, content, embedding <=> %s AS distance
            FROM {table}
            WHERE url = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT 2
        """

        params = (
            query_vector,
            link,
            query_vector,
        )

    elif link.startswith("https://discourse.onlinedegree.iitm.ac.in/t/"):
        table = TABLES["discourse"]

        query = f"""
            SELECT url, parent_url, content, embedding <=> %s AS distance
            FROM {table}
            WHERE (url = %s OR parent_url = %s)
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT 2
        """

        params = (
            query_vector,
            link,
            link,
            query_vector,
        )

    else:
        return [{"error": "link not supported"}]

    try:
        with conn.cursor() as cur:
            cur.execute(query, params)

            rows = cur.fetchall()

            results = []

            for url, parent_url, content, distance in rows:
                similarity = 1 - distance

                results.append({
                    "url": url,
                    "parent_url": parent_url if table == TABLES["discourse"] else None,
                    "content": content,
                    "similarity": similarity
                })

            return results

    except Exception as e:
        print(f"Error searching link in {table}: {e}")
        return [{"error": str(e)}]

def fetch_surrounding_context(matches: list, link: str = "", window: int = 2) -> list:
    
    n = len(matches)
    for i in range(n):
        match = matches[i]
        url = match.get("url")

        discourse_prefix = "https://discourse.onlinedegree.iitm.ac.in/t/"
        m = re.match(r"^https://discourse\.onlinedegree\.iitm\.ac\.in/t/([^/]+)/(\d+)/(\d+)$", url)
        if m:
            slug = m.group(1)
            topic_id = m.group(2)
            post_id = int(m.group(3))

            for offset in range(-window, window + 1):
                if offset == 0:
                    continue
                new_post_id = post_id + offset
                new_url = f"{discourse_prefix}{slug}/{topic_id}/{new_post_id}"

                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT url, parent_url, content
                            FROM discourse_book
                            WHERE url = %s
                            LIMIT 1
                            """,
                            (new_url,)
                        )

                        row = cur.fetchone()

                        if row:
                            matches.append({
                                "url": row[0],
                                "parent_url": row[1],
                                "content": row[2]
                            })

                except Exception as e:
                    print(f"Could not fetch {new_url}: {e}")

    return matches

def get_image_mimetype(base64_string):
    image_data = base64.b64decode(base64_string)

    kind = filetype.guess(image_data)

    if kind is None:
        return "application/octet-stream"

    return kind.mime

def ask_gpt(query: str, matches: list, image_input: str = None) -> str:
    context_str = "\n".join([m["content"] for m in matches])

    url = "https://aipipe.org/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    if image_input:
        mime_type = get_image_mimetype(image_input)

        messages = [
            {"role": "system", "content": "You are an assistant that answers questions using the given context. If the context does not have any answer, tell that you do not have the answer"},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {query}"},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_input}"}},
                    {"type": "text", "text": "The image is attached above. Use this image along with the context to answer the question."}
                ]
            }
        ]

    else:
        messages = [
            {"role": "system", "content": "You are an assistant that answers questions using the given context. If the context does not have any answer, tell that you do not have the answer"},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuestion: {query}"}
        ]

    data = {
        "model": "gpt-4o-mini",
        "messages": messages
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]


@app.get('/')
async def default():
    return {"message": "server is running"}

@app.get("/boot")
async def boot_status():
    # Startup messages + a live database ping, for the frontend terminal.
    def ping():
        start = time.time()
        conn.execute("SELECT 1")
        return round((time.time() - start) * 1000, 1)

    try:
        db = {"ok": True, "ms": await run_in_threadpool(ping)}
    except Exception as e:
        print(f"[boot] database ping failed: {e}", flush=True)
        db = {"ok": False, "ms": None}

    return {
        "boot": BOOT_LOG,
        "db": db,
        "uptime": round(time.time() - START_TIME, 1),
    }

def _short_url(url: str, width: int = 78) -> str:
    return url if len(url) <= width else url[: width - 1] + "…"

def _source_of(match: dict) -> str:
    return "discourse" if (match.get("url") or "").startswith(DISCOURSE_LINK_PREFIX) else "course"

async def run_pipeline(payload: QueryRequest):
    """
    The whole question -> answer flow as an async generator of events:
      {"type": "log",    "t": seconds, "level": info|ok|warn|hit, "msg": str}
      {"type": "result", "t": seconds, "answer": str, "links": [...]}
      {"type": "error",  "t": seconds, "status": int, "msg": str}
    Each event is also printed to the server console.
    """
    rid = uuid.uuid4().hex[:6]
    t0 = time.time()

    def ev(level: str, msg: str) -> dict:
        print(f"[req {rid}] {msg}", flush=True)
        return {"type": "log", "t": round(time.time() - t0, 3), "level": level, "msg": msg}

    def err(status: int, msg: str) -> dict:
        print(f"[req {rid}] ERROR {status}: {msg}", flush=True)
        return {"type": "error", "t": round(time.time() - t0, 3), "status": status, "msg": msg}

    link = (payload.link or "").strip()

    try:
        yield ev("info", f"request {rid} received - question {len(payload.question)} chars, "
                         f"link {'provided' if link else 'none'}")

        if payload.image:
            validate_image_size(payload.image)
            yield ev("info", "image attached, size ok")

        yield ev("info", "checking daily API budget ...")
        if await daily_budget_exceeded():
            yield err(429, "API usage limit reached for today. Please try again tomorrow.")
            return
        yield ev("ok", "budget ok")

        yield ev("info", "embedding question with text-embedding-3-small ...")
        started = time.time()
        embedding = await run_in_threadpool(get_embedding, payload.question)
        yield ev("ok", f"embedding ready - {len(embedding)} dims in {time.time() - started:.2f}s")

        if link:
            if link.startswith(COURSE_LINK_PREFIX):
                yield ev("info", "link is a course page - searching course_content_book for that page ...")
            elif link.startswith(DISCOURSE_LINK_PREFIX):
                yield ev("info", "link is a discourse thread - searching discourse_book for that thread ...")
            else:
                yield err(400, "link not supported - use a tds.s-anand.net page "
                               "or a discourse.onlinedegree.iitm.ac.in/t/ thread")
                return
            started = time.time()
            matches = await run_in_threadpool(search_postgres_with_link, link, embedding)
            if matches and "error" in matches[0]:
                yield err(500, "database search failed - see the server logs")
                return
            if not matches:
                yield ev("warn", "no chunks found for that link - answering without context")
        else:
            yield ev("info", "no link - vector search across discourse_book + course_content_book (cosine, k=2) ...")
            started = time.time()
            matches = await run_in_threadpool(search_postgres_with_vector, embedding)

        yield ev("ok", f"{len(matches)} match(es) in {time.time() - started:.2f}s")
        for i, m in enumerate(matches, 1):
            yield ev("hit", f"#{i}  sim {m['similarity']:.3f}  {_source_of(m):<9}  {_short_url(m['url'])}")

        yield ev("info", "fetching surrounding discourse posts (+-2) ...")
        found = len(matches)
        more_matches = await run_in_threadpool(fetch_surrounding_context, matches, link)
        yield ev("ok", f"+{len(more_matches) - found} neighbouring post(s), context is {len(more_matches)} chunk(s)")

        context_chars = sum(len(m["content"]) for m in more_matches)
        yield ev("info", f"asking gpt-4o-mini - {context_chars:,} chars of context"
                         f"{' + image' if payload.image else ''} ...")
        started = time.time()
        gpt_answer = await run_in_threadpool(ask_gpt, payload.question, more_matches, payload.image)
        yield ev("ok", f"answer received - {len(gpt_answer['content'])} chars in {time.time() - started:.2f}s")

        links = [{"url": x["parent_url"] if x["parent_url"] else x["url"], "text": x["content"]} for x in more_matches[:3]]

        yield ev("ok", f"done in {time.time() - t0:.2f}s")
        yield {"type": "result", "t": round(time.time() - t0, 3),
               "answer": gpt_answer["content"], "links": links}

    except HTTPException as e:
        yield err(e.status_code, str(e.detail))
    except requests.HTTPError as e:
        traceback.print_exc()
        code = getattr(e.response, "status_code", "?")
        yield err(502, f"upstream API error ({code})")
    except Exception:
        traceback.print_exc()
        yield err(500, "internal error - see the server logs")

@app.post("/api")
async def handle_query(payload: QueryRequest):

    async for event in run_pipeline(payload):
        if event["type"] == "error":
            raise HTTPException(status_code=event["status"], detail=event["msg"])
        if event["type"] == "result":
            return {"answer": event["answer"],
                    "links": event["links"]}

@app.post("/api/stream")
async def handle_query_stream(payload: QueryRequest):
    # Same pipeline as /api, but every step is sent as it happens (one JSON object per line).
    async def lines():
        async for event in run_pipeline(payload):
            yield json.dumps(event) + "\n"

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

boot("ready - waiting for questions", "ok")

if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
