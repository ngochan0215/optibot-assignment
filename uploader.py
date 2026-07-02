import os
import glob
import time
from dotenv import load_dotenv
from google import genai
import chromadb

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Kết nối ChromaDB Cloud
chroma_client = chromadb.HttpClient(
    ssl=True,
    host="api.trychroma.com",
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    headers={"x-chroma-token": os.getenv("CHROMA_API_KEY")}
)
collection = chroma_client.get_or_create_collection(name="optibot-kb")
print(f"✓ ChromaDB Cloud sẵn sàng. Hiện có {collection.count()} chunks\n")

def make_chunks(text, chunk_size=1500, overlap=150):
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks

files = sorted(glob.glob("articles/*.md"))
print(f"Tìm thấy {len(files)} file .md\n")

total_chunks = 0
skipped = 0
uploaded = 0

for file_idx, file_path in enumerate(files):
    slug = os.path.basename(file_path).replace(".md", "")

    existing = collection.get(ids=[f"{slug}_chunk_0"])
    if existing["ids"]:
        print(f"[{file_idx+1}/{len(files)}] SKIP: {slug}")
        skipped += 1
        continue

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    article_url = ""
    for line in content.splitlines():
        if line.startswith("Article URL:"):
            article_url = line.replace("Article URL:", "").strip()
            break

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
        total_chunks += 1

    uploaded += 1
    print(f"[{file_idx+1}/{len(files)}] ✓ {slug} ({len(chunks)} chunks)")
    time.sleep(0.5)

print(f"""
=============================
✅ HOÀN THÀNH!
  Uploaded : {uploaded} files
  Skipped  : {skipped} files
  Chunks   : {total_chunks} chunks mới
  DB total : {collection.count()} chunks
=============================
""")