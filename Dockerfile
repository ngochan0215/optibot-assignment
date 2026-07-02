FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p articles state chroma_db docs

# Chạy 1 lần rồi thoát (exit 0 = thành công)
ENTRYPOINT ["python", "main.py"]