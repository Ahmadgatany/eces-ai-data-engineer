import json
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from curl_cffi import requests

# ============================================================
# Configuration
# ============================================================

BASE_URL = "https://www.bayut.eg"

DATA_DIR = Path("data/raw")
URLS_FILE = DATA_DIR / "listing_urls.json"

# Failure log
FAILURE_LOG = Path("data/scraping_failures.jsonl")

REQUEST_DELAY = 1.0


TARGETS = {
    "cairo_sale": {
        "url": f"{BASE_URL}/en/cairo/properties-for-sale/",
        "target": 280,
    },
    "cairo_rent": {
        "url": f"{BASE_URL}/en/cairo/properties-for-rent/",
        "target": 70,
    },
    "giza_sale": {
        "url": f"{BASE_URL}/en/giza/properties-for-sale/",
        "target": 140,
    },
    "giza_rent": {
        "url": f"{BASE_URL}/en/giza/properties-for-rent/",
        "target": 70,
    },
    "alexandria_sale": {
        "url": f"{BASE_URL}/en/alexandria/properties-for-sale/",
        "target": 70,
    },
    "alexandria_rent": {
        "url": f"{BASE_URL}/en/alexandria/properties-for-rent/",
        "target": 70,
    },
}


# ============================================================
# Persistence
# ============================================================

def load_saved_urls():
    """Load previously collected listing URLs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not URLS_FILE.exists():
        return {key: [] for key in TARGETS}

    with open(URLS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Make sure all expected keys exist.
    for key in TARGETS:
        data.setdefault(key, [])

    return data


def save_urls(data: dict) -> None:
    """Save collected listing URLs to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(URLS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


# ============================================================
# Failure Logging
# ============================================================

def log_failure(
    target_name: str,
    page_number: int,
    url: str,
    error: str,
):
    """Append a scraping failure to the JSONL log."""
    FAILURE_LOG.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "target": target_name,
        "page": page_number,
        "url": url,
        "error": error,
    }

    with open(FAILURE_LOG, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


# ============================================================
# HTTP
# ============================================================

def fetch_page(url: str):
    """Fetch a Bayut page using a browser-like TLS fingerprint."""
    response = requests.get(
        url,
        impersonate="chrome",
        timeout=30,
    )

    response.raise_for_status()

    return response


# ============================================================
# Parsing
# ============================================================

def parse_page(html: str):
    """Parse HTML using BeautifulSoup."""
    return BeautifulSoup(html, "lxml")


# ============================================================
# Listing URL Extraction
# ============================================================

def extract_listing_urls(soup: BeautifulSoup):
    """Extract unique property listing URLs."""
    listing_urls = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/property/" not in href:
            continue

        full_url = urljoin(BASE_URL, href)

        if full_url not in seen:
            seen.add(full_url)
            listing_urls.append(full_url)

    return listing_urls


# ============================================================
# Pagination
# ============================================================

def get_page_url(base_url: str, page_number: int):
    """Build a Bayut pagination URL."""
    if page_number == 1:
        return base_url

    return urljoin(
        BASE_URL,
        f"{base_url.rstrip('/')}/page-{page_number}/"
    )


# ============================================================
# Collect One Target
# ============================================================

def collect_target(
    target_name: str,
    config: dict,
    saved_data: dict,
):
    """
    Collect listing URLs for one governorate/purpose slice.
    Resumes from existing saved URLs and avoids duplicates.
    """
    target_count = config["target"]
    base_url = config["url"]

    existing_urls = saved_data[target_name]

    # Deduplicate existing data in case the file was manually modified.
    existing_urls = list(dict.fromkeys(existing_urls))

    saved_data[target_name] = existing_urls

    if len(existing_urls) >= target_count:
        print(f"\n[{target_name}] Already complete: {len(existing_urls)}/{target_count}")
        return

    print("\n" + "=" * 70)
    print(f"COLLECTING: {target_name}")
    print("=" * 70)

    print(f"Target: {target_count}")
    print(f"Already saved: {len(existing_urls)}")
    print(f"Base URL: {base_url}")

    collected = set(existing_urls)

    page_number = 1

    while len(collected) < target_count:
        page_url = get_page_url(base_url, page_number)

        print("\n" + "-" * 70)
        print(f"Page {page_number}")
        print(f"URL: {page_url}")

        try:
            response = fetch_page(page_url)

        except Exception as exc:
            error_message = str(exc)

            print(f"Request failed on page {page_number}: {error_message}")

            log_failure(
                target_name=target_name,
                page_number=page_number,
                url=page_url,
                error=error_message,
            )

            break

        soup = parse_page(response.text)

        page_urls = extract_listing_urls(soup)

        print(f"Listings found on page: {len(page_urls)}")

        if not page_urls:
            print("No listings found. Stopping this target.")
            break

        new_urls = [url for url in page_urls if url not in collected]

        print(f"New unique listings: {len(new_urls)}")

        for url in new_urls:
            if len(collected) >= target_count:
                break

            collected.add(url)

        saved_data[target_name] = list(collected)

        # Persist after every page.
        save_urls(saved_data)

        print(f"Progress: {len(collected)}/{target_count}")

        if len(collected) >= target_count:
            break

        page_number += 1

        time.sleep(REQUEST_DELAY)

    print(f"\nFinished {target_name}: {len(collected)}/{target_count}")


# ============================================================
# Main
# ============================================================

def main():
    print("\n" + "=" * 70)
    print("BAYUT SCRAPER")
    print("=" * 70)

    print("\nTargets:")

    total_target = 0

    for name, config in TARGETS.items():
        print(f"  {name:<18} {config['target']}")
        total_target += config["target"]

    print(f"\nTotal target: {total_target}")

    # --------------------------------------------------------
    # Load existing URLs
    # --------------------------------------------------------
    saved_data = load_saved_urls()

    # --------------------------------------------------------
    # Collect each target
    # --------------------------------------------------------
    for target_name, config in TARGETS.items():
        collect_target(
            target_name,
            config,
            saved_data
        )

    # --------------------------------------------------------
    # Final Summary
    # --------------------------------------------------------
    print("\n" + "=" * 70)
    print("FINAL SCRAPING SUMMARY")
    print("=" * 70)

    total_collected = 0

    for target_name, config in TARGETS.items():
        count = len(saved_data[target_name])
        target = config["target"]

        total_collected += min(count, target)

        status = "COMPLETE" if count >= target else "INCOMPLETE"

        print(f"{target_name:<18} {count:>4}/{target:<4} {status}")

    print("-" * 70)
    print(f"TOTAL: {total_collected}/700")
    print(f"\nSaved to: {URLS_FILE}")


if __name__ == "__main__":
    main()