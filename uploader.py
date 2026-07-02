import os
import glob
import time
from dotenv import load_dotenv
from google import genai
import chromadb

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# =========================================
# Khởi tạo ChromaDB
# =========================================
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="optibot-kb")
print(f"✓ ChromaDB sẵn sàng. Hiện có {collection.count()} chunks\n")

# =========================================
# Hàm cắt text thành chunks
# =========================================
def make_chunks(text, chunk_size=1500, overlap=150):
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks

# =========================================
# Upload tất cả file .md
# =========================================
files = sorted(glob.glob("articles/*.md"))
print(f"Tìm thấy {len(files)} file .md\n")

total_chunks = 0
skipped      = 0
uploaded     = 0

for file_idx, file_path in enumerate(files):
    slug = os.path.basename(file_path).replace(".md", "")

    # Bỏ qua nếu đã upload rồi (kiểm tra chunk đầu tiên)
    existing = collection.get(ids=[f"{slug}_chunk_0"])
    if existing["ids"]:
        print(f"[{file_idx+1}/{len(files)}] SKIP (đã có): {slug}")
        skipped += 1
        continue

    # Đọc file
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Lấy Article URL để dùng làm citation
    article_url = ""
    for line in content.splitlines():
        if line.startswith("Article URL:"):
            article_url = line.replace("Article URL:", "").strip()
            break

    # Cắt thành chunks
    chunks = make_chunks(content)

    # Embed và lưu từng chunk
    for i, chunk_text in enumerate(chunks):
        result = client.models.embed_content(
            model="gemini-embedding-2",
            contents=chunk_text,
        )
        embedding = result.embeddings[0].values

        collection.add(
            ids=[f"{slug}_chunk_{i}"],
            embeddings=[embedding],
            documents=[chunk_text],
            metadatas=[{
                "source": article_url,
                "slug": slug,
                "chunk": i
            }]
        )
        total_chunks += 1

    uploaded += 1
    print(f"[{file_idx+1}/{len(files)}] ✓ {slug} ({len(chunks)} chunks)")

    # Nghỉ 0.5s sau mỗi file để tránh rate limit
    time.sleep(0.5)

# =========================================
# Tổng kết
# =========================================
print(f"""
=============================
✅ HOÀN THÀNH!
  Uploaded : {uploaded} files
  Skipped  : {skipped} files (đã có sẵn)
  Chunks   : {total_chunks} chunks mới
  Tổng DB  : {collection.count()} chunks
=============================
""")