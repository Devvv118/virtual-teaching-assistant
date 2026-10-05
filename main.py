import os
import re
import httpx
import base64
import filetype
import requests
import typesense
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from typing import List, Optional
from fastapi import HTTPException
from datetime import date, timedelta
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

DAILY_LIMIT = 10
MAX_QUESTION_LENGTH = 20_000
MAX_IMAGE_SIZE = 20 * 1024 * 1024

api_key = os.getenv("AIPIPE_TOKEN")
typesense_api_key = os.getenv("TYPESENSE_ADMIN_KEY")
typesense_host = os.getenv("TYPESENSE_HOST")

typesense_client = typesense.Client({
    "nodes": [{
        "host": typesense_host,
        "port": "443",
        "protocol": "https"
    }],
    "api_key": typesense_api_key,
    "connection_timeout_seconds": 10
})

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["OPTIONS", "POST", "GET"],
    allow_headers=["*"],
)

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
            yesterday = today - timedelta(days=1)

            today = today.isoformat()
            yesterday = yesterday.isoformat()

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

def cosine_sim(vec1: List[float], vec2: List[float]) -> float:
    a = np.array(vec1)
    b = np.array(vec2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

def search_typesense_with_vector(embedding: list, k=2) -> list:
    query_vector = ",".join(map(str, embedding))

    collections = ["discourse-book", "course-content-book"]
    all_hits = []

    for collection in collections:
        results = typesense_client.multi_search.perform({
            "searches": [
                {
                    "collection": collection,
                    "q": "placeholder",
                    "query_by": "content",
                    "vector_query": f"embedding:([{query_vector}], k:{k})"
                }
            ]
        })

        if "error" in results:
            print(f"Typesense error in {collection}:")
            print(result["error"])
            continue

        hits = results["results"][0]["hits"]
        for hit in hits:
            doc = hit["document"]
            doc_embedding = doc.get("embedding")
            if doc_embedding:
                sim = cosine_sim(embedding, doc_embedding)
                all_hits.append({
                    "url": doc.get("url"),
                    "parent_url": doc["parent_url"] if collection=="discourse-book" else None,
                    "content": doc["content"],
                    "similarity": sim
                })

    sorted_hits = sorted(all_hits, key=lambda x: x["similarity"], reverse=True)
    return sorted_hits[:k]

def search_typesense_with_link(link: str, query_embedding: list) -> list:
    all_hits = []
    search_config = None

    if link.startswith("https://tds.s-anand.net/#/"):
        collection = "course-content-book"
        search_config = {
            "q": "*",
            "query_by": "content",
            "filter_by": f"url:={link}"
        }

    elif link.startswith("https://discourse.onlinedegree.iitm.ac.in/t/"):
        collection = "discourse-book"
        search_config = {
            "q": "*",
            "query_by": "content",
            "filter_by": f"url:={link} || parent_url:={link}"
        }

    else:
        return [{"error": "link not supported"}]

    try:
        result = typesense_client.collections[collection].documents.search(search_config)

        for hit in result.get("hits", []):
            doc = hit.get("document", {})
            doc_embedding = doc.get("embedding")

            if doc_embedding:
                sim = cosine_sim(query_embedding, doc_embedding)
                all_hits.append({
                    "url": doc.get("url"),
                    "parent_url": doc.get("parent_url") if collection=="discourse-book" else None,
                    "content": doc.get("content"),
                    "similarity": sim
                })

    except Exception as e:
        print(f"Error searching link in {collection}: {e}")
        return [{"error": str(e)}]

    return sorted(all_hits, key=lambda x: x["similarity"], reverse=True)[:2]

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
                    result = typesense_client.collections["discourse-book"].documents.search({
                        "q": "*",
                        "query_by": "content",
                        "filter_by": f"url:={new_url}"
                    })
                    for hit in result.get("hits", []):
                        doc = hit["document"]

                        if doc.get("url") == new_url:
                            matches.append({
                                "url": doc["url"],
                                "parent_url": doc["parent_url"],
                                "content": doc["content"]
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
    
    return mime_type # eg. image/webp

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

@app.post("/api")
async def handle_query(payload: QueryRequest):

    if payload.image:
        validate_image_size(payload.image)

    if await daily_budget_exceeded():
        raise HTTPException(
            status_code=429,
            detail="API usage limit reached for today. Please try again tomorrow."
        )

    embedding = get_embedding(payload.question)
    if(payload.link):
        matches = search_typesense_with_link(payload.link,embedding)
        more_matches = fetch_surrounding_context(matches,payload.link)
    else:
        matches = search_typesense_with_vector(embedding)
        more_matches = fetch_surrounding_context(matches)
    
    gpt_answer = ask_gpt(payload.question, more_matches, payload.image)

    links = [{"url":x["parent_url"] if x["parent_url"] else x["url"] , "text":x["content"]} for x in more_matches[:3]]

    return {"answer": gpt_answer["content"], 
            "links": links}