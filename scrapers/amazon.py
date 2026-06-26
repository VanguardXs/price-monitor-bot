import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENWEBNINJA_API_KEY")
BASE_URL = "https://api.openwebninja.com/realtime-amazon-data/search"


def search_amazon(query: str, limit: int = 3) -> list[dict]:
    """
    Search for a product on Amazon and return a list of results
    with normalized fields: source, title, price, rating, reviews, url
    """
    headers = {"x-api-key": API_KEY}
    params = {"query": query, "page": 1}

    try:
        response = requests.get(BASE_URL, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        products = data.get("data", {}).get("products", [])

        results = []
        for item in products[:limit]:
            price_str = item.get("product_price", "0")
            price = _parse_price(price_str)

            results.append({
                "source": "Amazon",
                "title": item.get("product_title", ""),
                "price": price,
                "rating": item.get("product_star_rating", 0) or 0,
                "reviews": item.get("product_num_ratings", 0) or 0,
                "url": item.get("product_url", "")
            })
        return results

    except Exception as e:
        print(f"❌ Amazon search error for '{query}': {e}")
        return []


def _parse_price(price_str) -> float:
    """Convert price string like '$799.00' into a float"""
    if not price_str:
        return 0.0
    try:
        clean = str(price_str).replace("$", "").replace(",", "").strip()
        return float(clean)
    except (ValueError, TypeError):
        return 0.0


if __name__ == "__main__":
    results = search_amazon("iphone 15")
    for r in results:
        print(r)