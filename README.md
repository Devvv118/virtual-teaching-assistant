# Virtual Teaching Assistant

A retrieval-augmented (RAG) question-answering API for the **Tools in Data Science (TDS)** course at IIT Madras. Students post a question (optionally with a screenshot and/or a link to a course page or Discourse thread), and the service answers it using the course material and past Discourse forum discussions as context.

## How it works

```
                 ┌──────────────────────────────┐
                 │  POST /api                   │
                 │  question, image?, link?     │
                 └──────────────┬───────────────┘
                                │
                  1. Embed question (text-embedding-3-small)
                                │
                  2. Vector search in Typesense
                     ├─ no link  → search both collections
                     └─ link     → search only that page / thread
                                │
                  3. Pull in neighbouring Discourse posts
                     (±2 posts around each hit) for context
                                │
                  4. Ask gpt-4o-mini with the retrieved context
                     (+ the image, if one was supplied)
                                │
                 ┌──────────────▼───────────────┐
                 │  { answer, links[] }         │
                 └──────────────────────────────┘
```

Two Typesense collections back the search:

| Collection | Source | Notes |
|---|---|---|
| `course-content-book` | Course site at `tds.s-anand.net` | Pages split into 300-token chunks |
| `discourse-book` | IITM Discourse forum posts | One document per post, with `parent_url` pointing to the topic |

LLM and embedding calls go through an OpenAI-compatible proxy (`aiproxy.sanand.workers.dev`).

## Project structure

```
virtual-teaching-assistant/
├── main.py                     # FastAPI app (the API server)
├── requirements.txt
├── LICENSE
└── fetching-data/              # One-off data pipeline scripts
    ├── course-content/
    │   ├── 1._sidebar.md           # Course sidebar (list of all course pages)
    │   ├── 2.urlCreator.py         # Sidebar → urls.txt
    │   ├── 3.createJsonl.py        # Download each page → Jan25-Data.jsonl
    │   ├── 4.chunker300.py         # Split into 300-token chunks → Jan25-chunked.jsonl
    │   ├── 5.EmbedCourseContent.py # Embed chunks and upload to Typesense
    │   ├── urls.txt
    │   ├── Jan25-Data.jsonl
    │   └── Jan25-chunked.jsonl
    └── discourse-content/
        ├── discourse-data.jsonl    # Scraped Discourse posts
        └── EmbedDiscourse.py       # Embed posts and upload to Typesense
```

## Setup

### Prerequisites

- Python 3.9 – 3.12 (`main.py` uses `imghdr`, which was removed in Python 3.13)
- A [Typesense](https://typesense.org/) cluster (the code is currently pointed at a Typesense Cloud host, see [Configuration](#configuration))
- An API token for the AI proxy

### Install

```bash
git clone <your-repo-url>
cd virtual-teaching-assistant

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install tiktoken             # only needed for the chunking script
```

### Configuration

Create a `.env` file in the project root:

```env
AIPROXY_TOKEN=your_ai_proxy_token
TYPESENSE_ADMIN_KEY=your_typesense_admin_api_key
```

The Typesense host is hard-coded as `typesense_host` at the top of `main.py`, `5.EmbedCourseContent.py` and `EmbedDiscourse.py`. Change it in all three if you use your own cluster.

## Building the search index

The repo already includes the scraped data (`Jan25-Data.jsonl`, `Jan25-chunked.jsonl`, `discourse-data.jsonl`), so you can skip straight to the embedding steps. To rebuild the course content from scratch, run the numbered scripts in order from inside `fetching-data/course-content/`:

```bash
cd fetching-data/course-content

python 2.urlCreator.py          # parse 1._sidebar.md  → urls.txt
python 3.createJsonl.py         # fetch every page     → Jan25-Data.jsonl
python 4.chunker300.py          # chunk to 300 tokens  → Jan25-chunked.jsonl
python 5.EmbedCourseContent.py  # embed + upload to Typesense
```

Then index the Discourse posts:

```bash
cd ../discourse-content
python EmbedDiscourse.py
```

> **Note:** both embed scripts begin by **deleting** their collection before recreating it. On a brand-new Typesense cluster that first `delete()` call will raise an error because the collection doesn't exist yet; wrap it in a `try/except` or comment it out for the first run.

### Data formats

Course content (`Jan25-chunked.jsonl`):

```json
{"url": "https://tds.s-anand.net/#/README", "content": "..."}
```

Discourse posts (`discourse-data.jsonl`):

```json
{"id": 579338, "username": "...", "content": "...", "created_at": "2025-01-13T15:40:50.279Z",
 "parent_url": "https://discourse.onlinedegree.iitm.ac.in/t/<slug>/<topic_id>",
 "url": "https://discourse.onlinedegree.iitm.ac.in/t/<slug>/<topic_id>/<post_number>"}
```

## Running the server

```bash
uvicorn main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/
# {"message": "server is running"}
```

## API reference

### `POST /api`

**Request body (JSON)**

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | yes | The student's question |
| `image` | string | no | Base64-encoded image (PNG, JPEG, WebP, etc.) to include with the question |
| `link` | string | no | A course page (`https://tds.s-anand.net/#/...`) or Discourse topic (`https://discourse.onlinedegree.iitm.ac.in/t/...`). If given, retrieval is restricted to that page/thread |

**Response**

```json
{
  "answer": "Model-generated answer...",
  "links": [
    { "url": "https://discourse.onlinedegree.iitm.ac.in/t/...", "text": "Matching content..." }
  ]
}
```

`links` contains up to three source references (the Discourse topic URL for forum posts, or the page URL for course content).

**Example**

```bash
curl -X POST http://localhost:8000/api \
  -H "Content-Type: application/json" \
  -d '{"question": "Which tool should I use to run Python scripts with inline dependencies?"}'
```

With an image:

```bash
IMG=$(base64 -w0 screenshot.png)   # macOS: base64 -i screenshot.png
curl -X POST http://localhost:8000/api \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"What does this error mean?\", \"image\": \"$IMG\"}"
```

If a `link` points to an unsupported domain, retrieval returns an error entry rather than results.

## Tech stack

- **[FastAPI](https://fastapi.tiangolo.com/)** + Uvicorn – web API
- **[Typesense](https://typesense.org/)** – vector store / search
- **OpenAI `text-embedding-3-small`** – embeddings (1536 dimensions)
- **OpenAI `gpt-4o-mini`** – answer generation (text and vision)
- **NumPy** – cosine-similarity re-ranking
- **tiktoken** – token-based chunking

## Known limitations

- CORS is open to all origins (`allow_origins=["*"]`); restrict it before deploying publicly.
- The Discourse scraper isn't included, only its output (`discourse-data.jsonl`).
- Retrieval takes the top 2 hits plus up to 4 neighbouring Discourse posts per hit; there's no score threshold, so low-relevance context can still reach the model.
- `requirements.txt` is unpinned and doesn't list `tiktoken`.

## License

Released under the [MIT License](LICENSE).
