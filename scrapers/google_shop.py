import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENWEBNINJA_API_KEY")
BASE_URL = "https://api.openwebninja.com/realtime-product-search/search-v2"


def search_google_shopping(query: str, limit: int = 3) -> list[dict]:
    """
    Search for a product on Google Shopping and return a list of results
    with normalized fields: source, title, price, rating, reviews, url
    """
    headers = {"x-api-key": API_KEY}
    params = {"q": query, "country": "us", "language": "en", "page": 1}

    try:
        response = requests.get(BASE_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        products = data.get("data", {}).get("products", [])

        results = []
        for item in products[:limit]:
            price = _parse_price(item.get("price", 0))

            results.append({
                "source": item.get("store_name") or "Google Shopping",
                "title": item.get("product_title", ""),
                "price": price,
                "rating": item.get("product_rating", 0) or 0,
                "reviews": item.get("product_num_reviews", 0) or 0,
                "url": item.get("product_page_url", "")
            })
        return results

    except Exception as e:
        print(f"❌ Google Shopping search error for '{query}': {e}")
        return []


def _parse_price(price_value) -> float:
    """Convert price (string or number) into a float"""
    if not price_value:
        return 0.0
    try:
        clean = str(price_value).replace("$", "").replace(",", "").strip()
        return float(clean)
    except (ValueError, TypeError):
        return 0.0


if __name__ == "__main__":
    results = search_google_shopping("iphone 15")
    for r in results:
        print(r)