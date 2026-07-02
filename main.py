"""
main.py - Daily job
Chạy 1 lần mỗi ngày:
1. Scrape lại toàn bộ bài từ support.optisigns.com
2. Phát hiện bài nào mới / đã sửa / không đổi (so sánh hash)
3. Chỉ upload delta lên ChromaDB
4. Log kết quả
"""

import os
import re
import glob
import json
import time
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import requests
from markdownify import markdownify as html_to_md
from google import genai
import chromadb

load_dotenv()

# config
ARTICLES_DIR = "articles"
STATE_FILE   = "state/article_state.json"
CHUNK_SIZE   = 1500
OVERLAP      = 150

client       = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection   = chroma_client.get_or_create_collection(name="optibot-kb")

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
    """Xóa toàn bộ chunks của 1 bài trong ChromaDB"""
    existing = collection.get(where={"slug": slug})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

def upload_article(slug, content, article_url):
    """Embed và lưu các chunks của 1 bài vào ChromaDB"""
    chunks = make_chunks(content)
    for i, chunk_text in enumerate(chunks):
        result = client.models.embed_content(
            model="gemini-embedding-2",
            contents=chunk_text,
        )
        collection.add(
            ids=[f"{slug}_chunk_{i}"],
            embeddings=[result.embeddings[0].values],
            documents=[chunk_text],
            metadatas=[{"source": article_url, "slug": slug, "chunk": i}]
        )
    return len(chunks)

# scrape section
print("=" * 50)
print("BƯỚC 1: Scraping support.optisigns.com...")
print("=" * 50)

all_articles = []
url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100"

while url:
    resp = requests.get(url, timeout=30)
    data = resp.json()
    for article in data["articles"]:
        if not article.get("draft"):
            all_articles.append(article)
    url = data.get("next_page")
    time.sleep(0.2)

print(f"Fetched {len(all_articles)} articles\n")

# detect delta section by comparing hash of content
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

    # save file .md
    Path(f"{ARTICLES_DIR}/{slug}.md").write_text(content, encoding="utf-8")

    # compare hash
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
print("BƯỚC 3: Uploading delta to ChromaDB...")

total_chunks = 0

for slug, content, url in new_articles:
    chunks = upload_article(slug, content, url)
    total_chunks += chunks
    print(f"  [NEW]     {slug} ({chunks} chunks)")
    time.sleep(0.3)

for slug, content, url in updated_articles:
    delete_chunks(slug)
    chunks = upload_article(slug, content, url)
    total_chunks += chunks
    print(f"  [UPDATED] {slug} ({chunks} chunks)")
    time.sleep(0.3)

# save new state and log 
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