import requests
import re
import os
from markdownify import markdownify as html_to_md

ARTICLES_DIR = "articles"   # thư mục lưu file markdown
MIN_ARTICLES = 30           # lấy ít nhất 30 bài

# create the folder to store the articles if it doesn't exist
os.makedirs(ARTICLES_DIR, exist_ok=True)

# make markdown file's name from title and article id
def make_slug(title, article_id):
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)   # thay ký tự lạ bằng dấu -
    slug = re.sub(r"-{2,}", "-", slug)          # bỏ dấu -- liên tiếp
    slug = slug.strip("-")[:80]                 # giới hạn 80 ký tự
    return slug or f"article-{article_id}"

# convert HTML to Markdown
def html_to_markdown(html):
    if not html:
        return ""

    # delete script and style
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>",  "", html, flags=re.S | re.I)

    # convert to markdown
    md = html_to_md(html, heading_style="ATX", bullets="-")

    # clean up markdown: remove trailing spaces, reduce multiple newlines to 2, and ensure it ends with a newline
    md = "\n".join(line.rstrip() for line in md.splitlines())
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md

# get all articles from Zendesk API (automatically paginate through pages)
print("Đang lấy bài từ support.optisigns.com...")

all_articles = []
url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?per_page=100"

while url:
    response = requests.get(url, timeout=30)
    data = response.json()

    for article in data["articles"]:
        if not article.get("draft"):          # skip draft articles
            all_articles.append(article)

    url = data.get("next_page")               # get next page URL
    print(f"  Đã lấy {len(all_articles)} bài...")

    if len(all_articles) >= MIN_ARTICLES and not url:
        break

print(f"\nTổng cộng: {len(all_articles)} bài")

# convert to markdown and save to files
print("\nĐang convert và lưu file Markdown...")

for article in all_articles:
    title      = article.get("title", "Untitled")
    article_id = article["id"]
    html_url   = article.get("html_url", "")
    updated_at = article.get("updated_at", "")
    body_html  = article.get("body", "")

    slug     = make_slug(title, article_id)
    body_md  = html_to_markdown(body_html)

    # file content: title + metadata + body
    content = f"""# {title}

Article URL: {html_url}
Last Updated: {updated_at}

---

{body_md}"""

    # save file
    file_path = os.path.join(ARTICLES_DIR, f"{slug}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  ✓ {slug}.md")

print(f"\nXong! Đã lưu {len(all_articles)} file vào thư mục '{ARTICLES_DIR}/'")