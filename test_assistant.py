import os
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

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

def ask_optibot(question: str):
    print(f"\n{'='*60}")
    print(f"Q: {question}")
    print('='*60)

    result = client.models.embed_content(
        model="gemini-embedding-2",
        contents=question,
    )
    question_embedding = result.embeddings[0].values

    search_results = collection.query(
        query_embeddings=[question_embedding],
        n_results=5,
    )

    context_parts = []
    sources = []
    for i, (doc, meta) in enumerate(zip(
        search_results["documents"][0],
        search_results["metadatas"][0]
    )):
        context_parts.append(f"[Đoạn {i+1}]\n{doc}")
        if meta["source"] and meta["source"] not in sources:
            sources.append(meta["source"])

    context = "\n\n".join(context_parts)

    prompt = f"""Dựa vào các đoạn tài liệu sau đây để trả lời câu hỏi.

=== TÀI LIỆU THAM KHẢO ===
{context}

=== CÂU HỎI ===
{question}

Sau khi trả lời, liệt kê các Article URL nguồn theo format:
Article URL: <url>"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config={"system_instruction": SYSTEM_PROMPT},
        contents=prompt,
    )

    print("\nA:")
    print(response.text)
    print('='*60)

ask_optibot("How do I add a YouTube video?")