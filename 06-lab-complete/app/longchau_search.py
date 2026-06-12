"""
Long Chau product search via internal search API.
Returns top N products with name, price, and product URL.
"""

import httpx

_BASE_URL = "https://nhathuoclongchau.com.vn"
_SEARCH_API = "https://api.nhathuoclongchau.com.vn/lccus/search-product-service/api/products/ecom/product/search"

_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "order-channel": "1",
    "origin": "https://nhathuoclongchau.com.vn",
    "referer": "https://nhathuoclongchau.com.vn/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "x-channel": "EStore",
}


def _format_price(price_obj: dict) -> str:
    price = price_obj.get("price", 0)
    unit = price_obj.get("measureUnitName", "")
    symbol = price_obj.get("currencySymbol", "đ")
    return f"{int(price):,}{symbol}/{unit}" if unit else f"{int(price):,}{symbol}"


async def search_products(keyword: str, max_results: int = 3) -> list[dict]:
    """
    Search Long Chau products by keyword.
    Returns list of {name, price, url, image} dicts. Empty list on failure.
    """
    payload = {
        "isAutoCorrect": True,
        "keyword": keyword,
        "maxResultCount": max_results,
        "skipCount": 0,
        "sortType": 4,
        "codes": ["category", "manufactor", "brand"],
        "suggestSize": 3,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(_SEARCH_API, headers=_HEADERS, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    products = []
    for item in data.get("products", [])[:max_results]:
        slug = item.get("slug", "")
        if not slug:
            continue
        price_obj = item.get("price") or {}
        products.append({
            "name": item.get("webName") or item.get("name", ""),
            "price": _format_price(price_obj),
            "url": f"{_BASE_URL}/{slug}",
            "image": item.get("image", ""),
        })

    return products
