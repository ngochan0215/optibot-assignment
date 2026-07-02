import os
import glob
from dotenv import load_dotenv
from google import genai
import chromadb

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# set up chromadb client
print("Khởi tạo ChromaDB...")
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# create collection
collection = chroma_client.get_or_create_collection(name="optibot-kb")
print(f"✓ Collection 'optibot-kb' sẵn sàng")

# get random .md file from articles
files = glob.glob("articles/*.md")
if not files:
    raise RuntimeError("Không tìm thấy file .md trong thư mục articles/")

test_file = files[0]
print(f"\nĐang upload thử file: {test_file}")

with open(test_file, "r", encoding="utf-8") as f:
    content = f.read()

# get article URL from the first line of the file for citation
article_url = ""
for line in content.splitlines():
    if line.startswith("Article URL:"):
        article_url = line.replace("Article URL:", "").strip()
        break

print(f"Article URL: {article_url}")

# cut content into chunks 
CHUNK_SIZE = 1500
OVERLAP    = 150

chunks_text = []
start = 0
while start < len(content):
    end = start + CHUNK_SIZE
    chunks_text.append(content[start:end])
    start += CHUNK_SIZE - OVERLAP

print(f"File được cắt thành {len(chunks_text)} chunks")

# create embedding for each chunk and save to ChromaDB
slug = os.path.basename(test_file).replace(".md", "")

for i, chunk_text in enumerate(chunks_text):
    # call gemini embedding model
    result = client.models.embed_content(
        model="gemini-embedding-2",
        contents=chunk_text,
    )
    embedding = result.embeddings[0].values

    # save to ChromaDB
    collection.add(
        ids=[f"{slug}_chunk_{i}"],           # ID duy nhất
        embeddings=[embedding],               # dãy số vector
        documents=[chunk_text],              # text gốc
        metadatas=[{"source": article_url,   # metadata để citation
                    "slug": slug,
                    "chunk": i}]
    )
    print(f"  ✓ Chunk {i+1}/{len(chunks_text)} embedded và lưu vào ChromaDB")

print(f"\n✅ Xong! Upload thử 1 file thành công.")
print(f"Tổng chunks trong collection: {collection.count()}")