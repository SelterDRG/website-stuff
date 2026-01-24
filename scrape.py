import json
import time
import re
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BookRatingsBot/1.0; +https://github.com/SelterDRG/website-stuff)"
}

# Change this to your actual filename:
BOOKS_FILE = "books(full-list).json"

# ---------- Helpers ----------

def _clean_int(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        raise ValueError(f"Could not parse int from: {text!r}")
    return int(digits)

def _clean_float(text: str) -> float:
    t = text.strip().replace(",", ".")
    return float(t)

def pick_source_url(book: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (source, url) where source is 'goodreads' or 'royalroad' or None.
    Rules:
      - if book['url'] is not None -> use it (assumed Goodreads in your dataset)
      - else if vendors.rr.url exists -> use RoyalRoad URL
      - else -> None
    """
    primary = book.get("url")
    if primary:
        return "goodreads", primary

    vendors = book.get("vendors") or {}
    rr = vendors.get("rr") or {}
    rr_url = rr.get("url")
    if rr_url:
        return "royalroad", rr_url

    return None, None

# ---------- Goodreads scraping ----------

def scrape_goodreads(url: str) -> Tuple[float, int]:
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Average rating: <div class="RatingStatistics__rating" aria-hidden="true">5.00</div>
    rating_div = soup.find("div", class_="RatingStatistics__rating")
    if not rating_div:
        rating_div = soup.find("div", class_=lambda x: x and "RatingStatistics__rating" in x)
    if not rating_div:
        raise ValueError("Goodreads: rating element not found")

    rating_value = _clean_float(rating_div.get_text(strip=True))

    # Ratings count: <span data-testid="ratingsCount" ...>4 ratings</span>
    count_span = soup.find("span", {"data-testid": "ratingsCount"})
    if not count_span:
        raise ValueError("Goodreads: ratingsCount element not found")

    count_text = count_span.get_text(" ", strip=True)
    rating_count = _clean_int(count_text)

    return rating_value, rating_count

# ---------- RoyalRoad scraping ----------

def scrape_royalroad(url: str) -> Tuple[float, int]:
    resp = requests.get(url, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Score:
    score_span = soup.select_one('span[aria-label*="stars"]')
    if not score_span:
        raise ValueError("RoyalRoad: score span with aria-label not found")

    aria = (score_span.get("aria-label") or "").strip()
    data_content = (score_span.get("data-content") or "").strip()

    score_value: Optional[float] = None

    # aria-label example: "4.73 stars"
    m = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*stars", aria, flags=re.IGNORECASE)
    if m:
        score_value = _clean_float(m.group(1))
    else:
        # data-content example: "4.73 / 5"
        m2 = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*/\s*5", data_content)
        if m2:
            score_value = _clean_float(m2.group(1))

    if score_value is None:
        raise ValueError(f"RoyalRoad: could not parse score from aria-label={aria!r} data-content={data_content!r}")

    # Ratings count:
    lis = soup.select("ul.list-unstyled li")
    if not lis:
        lis = soup.find_all("li")

    rating_count: Optional[int] = None
    for i, li in enumerate(lis):
        key = li.get_text(" ", strip=True)
        key_norm = re.sub(r"\s+", " ", key).strip().lower()

        if key_norm in ("ratings :", "ratings:", "ratings"):
            # find next li with a number
            if i + 1 < len(lis):
                val_text = lis[i + 1].get_text(" ", strip=True)
                rating_count = _clean_int(val_text)
                break

    if rating_count is None:
        raise ValueError("RoyalRoad: could not locate 'Ratings' count in stats list")

    return score_value, rating_count

# ---------- Main ----------

def main():
    with open(BOOKS_FILE, encoding="utf-8") as f:
        books = json.load(f)

    updated = False
    failures = 0
    checked = 0

    for idx, book in enumerate(books, start=1):
        title = book.get("title", "UNKNOWN")

        source, url = pick_source_url(book)
        if not url or not source:
            print(f"[{idx}] Skipping (no Goodreads url, no RR vendor url): {title}")
            continue

        checked += 1
        print(f"[{idx}] Scraping ({source}): {title}")

        try:
            if source == "goodreads":
                rating, count = scrape_goodreads(url)
            else:
                rating, count = scrape_royalroad(url)

            rating_str = f"{rating:.2f}".rstrip("0").rstrip(".")
            count_str = str(count)

            old_rating = book.get("rating", "")
            old_count = book.get("r_count", "")

            print(f"     Found: ★ {rating_str} | {count_str} ratings")

            if old_rating != rating_str or old_count != count_str:
                book["rating"] = rating_str
                book["r_count"] = count_str
                updated = True
                print("     → Updated")
            else:
                print("     → No change")

            # Anti-DDOS delay
            time.sleep(2)

        except Exception as e:
            failures += 1
            print(f"     ERROR: {e}")

    if checked == 0:
        print("\nNo items had a Goodreads url or RR vendor url to scrape.")
        return

    if failures > checked * 0.3:
        print("\nWARNING: Many failures — site HTML may have changed or requests were blocked.")

    if updated:
        with open(BOOKS_FILE, "w", encoding="utf-8") as f:
            json.dump(books, f, indent=2, ensure_ascii=False)
        print("\nRatings updated and written to JSON.")
    else:
        print("\nNo updates made.")

if __name__ == "__main__":
    main()