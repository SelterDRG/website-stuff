import json
import time
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; BookRatingsBot/1.0; +https://github.com/SelterDRG/website-stuff)"
}

BOOKS_FILE = "books_full-list.json"

def scrape_goodreads(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # --- Average rating ---
    rating_div = soup.find("div", class_="RatingStatistics__rating")
    if not rating_div:
        rating_div = soup.find("div", class_=lambda x: x and "RatingStatistics__rating" in x)
    if not rating_div:
        raise ValueError("Rating element not found")

    rating_text = rating_div.get_text(strip=True)
    rating_value = float(rating_text.replace(",", "."))

    # --- Ratings count ---
    count_span = soup.find("span", {"data-testid": "ratingsCount"})
    if not count_span:
        raise ValueError("Ratings count element not found")

    count_text = count_span.get_text(" ", strip=True)
    count_digits = re.sub(r"[^\d]", "", count_text)
    if not count_digits:
        raise ValueError(f"Invalid ratings count: {count_text}")

    rating_count = int(count_digits)

    return rating_value, rating_count

def main():
    with open(BOOKS_FILE, encoding="utf-8") as f:
        books = json.load(f)

    updated = False
    failures = 0

    for book in books:
        url = book.get("url")
        if not url:
            continue

        try:
            rating, count = scrape_goodreads(url)

            rating_str = f"{rating:.2f}".rstrip("0").rstrip(".")
            count_str = str(count)

            if book.get("rating") != rating_str or book.get("r_count") != count_str:
                book["rating"] = rating_str
                book["r_count"] = count_str
                updated = True

            time.sleep(2)

        except Exception:
            failures += 1

    if failures > len(books) * 0.3:
        print("WARNING: Many failures - Goodreads layout may have changed!")

    if updated:
        with open(BOOKS_FILE, "w", encoding="utf-8") as f:
            json.dump(books, f, indent=4, ensure_ascii=False)
        print("Ratings updated.")
    else:
        print("No changes.")

if __name__ == "__main__":

    main()
