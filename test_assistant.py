import os
from dotenv import load_dotenv
from google import genai
import chromadb

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# connect chroma db
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="optibot-kb")

#  system prompt for optibot
SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

def ask_optibot(question: str):
    print(f"\n{'='*60}")
    print(f"Q: {question}")
    print('='*60)

    # Embed questions to vector
    result = client.models.embed_content(
        model="gemini-embedding-2",
        contents=question,
    )
    question_vector = result.embeddings[0].values

    # find 5 most relevant chunks in ChromaDB
    search_results = collection.query(
        query_embeddings=[question_vector],
        n_results=5,
    )

    # get relevant chunks and their sources
    relevant_chunks = search_results["documents"][0]
    sources         = search_results["metadatas"][0]

    # get up to 3 unique URLs for citation
    seen_urls = []
    for meta in sources:
        url = meta.get("source", "")
        if url and url not in seen_urls:
            seen_urls.append(url)
        if len(seen_urls) == 3:
            break

    # combine relevant chunks into context
    context = "\n\n---\n\n".join(relevant_chunks)

    # send to Gemini for answer generation
    prompt = f"""Use the following documentation to answer the question.

DOCUMENTATION:
{context}

QUESTION: {question}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        config={"system_instruction": SYSTEM_PROMPT},
        contents=prompt,
    )

    answer = response.text

    # print answer and sources
    print(f"\nA:\n{answer}")

    print("\nArticle URL:")
    for url in seen_urls:
        print(f"  - {url}")

    print('='*60)


# test the bot with a sample question
if __name__ == "__main__":
    ask_optibot("How do I add a YouTube video?")