import requests

url = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"

response = requests.get(url)
data = response.json()

print("So bai trong trang nay:", len(data["articles"]))
print("Co trang tiep theo khong:", data["next_page"])

# In thu bai dau tien de xem cau truc
first_article = data["articles"][0]
print("\n--- Bai dau tien ---")
print("Title:", first_article["title"])
print("URL:", first_article["html_url"])
print("Body (100 ky tu dau):", first_article["body"][:100])