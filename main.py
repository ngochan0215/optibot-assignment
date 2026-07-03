"""
main.py - Daily job
1. Scrape support.optisigns.com
2. Detect delta (hash comparison)
3. Upload only new/updated to ChromaDB Cloud
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import requests
from markdownify import markdownify as html_to_md
from google import genai
import chromadb
import logging
from google.genai.errors import ServerError, ClientError

# load environment variables
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)

required_env = [
    "GEMINI_API_KEY",
    "CHROMA_API_KEY",
    "CHROMA_TENANT",
    "CHROMA_DATABASE",
]

for key in required_env:
    if not os.getenv(key):
        raise RuntimeError(f"Missing environment variable: {key}")

# config
ARTICLES_DIR = "articles"
STATE_FILE   = "state/article_state.json"
CHUNK_SIZE   = 1500
OVERLAP      = 150

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Kết nối ChromaDB Cloud thay vì local
chroma_client = chromadb.HttpClient(
    ssl=True,
    host="api.trychroma.com",
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    headers={"x-chroma-token": os.getenv("CHROMA_API_KEY")}
)
collection = chroma_client.get_or_create_collection(name="optibot-kb")

os.makedirs(ARTICLES_DIR, exist_ok=True)
os.makedirs("state", exist_ok=True)

# helpers
def make_slug(title, article_id):
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:80]
    return slug or f"article-{article_id}"

def html_to_markdown(html):
    if not html:
        return ""
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>",   "", html, flags=re.S | re.I)
    md = html_to_md(html, heading_style="ATX", bullets="-")
    md = re.sub(r"!\[.*?\]\(.*?\)\n?", "", md)
    md = "\n".join(line.rstrip() for line in md.splitlines())
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md

def make_chunks(text):
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - OVERLAP
    return chunks

def load_state():
    if os.path.exists(STATE_FILE):
        return json.loads(Path(STATE_FILE).read_text())
    return {}

def save_state(state):
    Path(STATE_FILE).write_text(json.dumps(state, indent=2))

def delete_chunks(slug):
    existing = collection.get(
        where={"slug": slug},
        include=[]
    )
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

# Embed text with retry logic
def embed_with_retry(text, max_retries=5):
    # embed multiple chunks in one request to reduce API calls
    for attempt in range(max_retries):
        try:
            result = client.models.embed_content(
                model="gemini-embedding-2",
                contents=text,
            )
            return result.embeddings

        except ServerError:
            wait = 2 ** attempt
            logging.warning(
                f"Gemini unavailable. Retry after {wait}s..."
            )
            time.sleep(wait)

        except ClientError as e:
            print(type(e))
            print(dir(e))
            print(e)
            if e.status_code == 429:
                wait = min(60, 2 ** attempt)
                logging.warning(
                    f"Rate limited. Retry after {wait}s..."
                )
                time.sleep(wait)

            else:
                raise

    raise RuntimeError("Embedding failed after retries.")

def upload_article(slug, content, article_url):
    chunks = make_chunks(content)
    embeddings = embed_with_retry(chunks)
    ids = []
    vectors = []
    documents = []
    metadatas = []

    for i, embedding in enumerate(embeddings):
        ids.append(f"{slug}_chunk_{i}")
        vectors.append(embedding.values)
        documents.append(chunks[i])
        metadatas.append({
            "source": article_url,
            "slug": slug,
            "chunk": i
        })

    collection.add(
        ids=ids,
        embeddings=vectors,
        documents=documents,
        metadatas=metadatas
    )

    return len(chunks)

# scrape
print("=" * 50)
print("BƯỚC 1: Scraping support.optisigns.com...")
print("=" * 50)

all_articles = []
url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100"

while url:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    for article in data["articles"]:
        if not article.get("draft"):
            all_articles.append(article)
    url = data.get("next_page")
    time.sleep(0.2)

print(f"Fetched {len(all_articles)} articles\n")

# detect delta
print("BƯỚC 2: Detecting changes...")
old_state = load_state()
new_state = {}
new_articles     = []
updated_articles = []
unchanged        = []

for article in all_articles:
    title      = article.get("title", "Untitled")
    article_id = article["id"]
    html_url   = article.get("html_url", "")
    updated_at = article.get("updated_at", "")
    slug       = make_slug(title, article_id)
    body_md    = html_to_markdown(article.get("body", ""))

    content = f"# {title}\n\nArticle URL: {html_url}\nLast Updated: {updated_at}\n\n---\n\n{body_md}"
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    Path(f"{ARTICLES_DIR}/{slug}.md").write_text(content, encoding="utf-8")

    prev = old_state.get(slug)
    if prev is None:
        new_articles.append((slug, content, html_url))
    elif prev["hash"] != content_hash:
        updated_articles.append((slug, content, html_url))
    else:
        unchanged.append(slug)

    new_state[slug] = {"hash": content_hash, "url": html_url}

print(f"  New     : {len(new_articles)}")
print(f"  Updated : {len(updated_articles)}")
print(f"  Unchanged: {len(unchanged)}\n")

# upload delta
print("BƯỚC 3: Uploading delta to ChromaDB Cloud...")

total_chunks = 0

for slug, content, url in new_articles:

    try:
        chunks = upload_article(slug, content, url)
        total_chunks += chunks
        print(f"[NEW] {slug} ({chunks} chunks)")
        save_state(new_state)

    except Exception as e:
        logging.exception(
            f"Failed uploading article: {slug}"
        )

    time.sleep(0.5)

for slug, content, url in updated_articles:

    try:
        delete_chunks(slug)
        chunks = upload_article(
            slug,
            content,
            url
        )
        total_chunks += chunks
        print(f"[UPDATED] {slug} ({chunks} chunks)")
        save_state(new_state)

    except Exception:
        logging.exception(
            f"Failed updating article: {slug}"
        )

    time.sleep(0.5)
    
save_state(new_state)

print(f"""
{'='*50}
✅ JOB HOÀN THÀNH!
  Added   : {len(new_articles)} articles
  Updated : {len(updated_articles)} articles
  Skipped : {len(unchanged)} articles
  Chunks  : {total_chunks} chunks uploaded
  DB total: {collection.count()} chunks
{'='*50}
""")