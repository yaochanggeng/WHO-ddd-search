#!/usr/bin/env python3
"""
ATC/DDD Index scraper.

Crawls https://atcddd.fhi.no/atc_ddd_index/ and extracts:
  - Drug name (药品名称)
  - ATC code  (ATC编码)
  - Administration route (给药途径)
  - DDD value (DDD值)

Results are saved to atc_ddd_data.csv.
"""

import csv
import time
import logging
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://atcddd.fhi.no"
INDEX_URL = f"{BASE_URL}/atc_ddd_index/"
OUTPUT_FILE = "atc_ddd_data.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ATC-DDD-Scraper/1.0; "
        "+https://github.com/yaochanggeng/WHO-ddd-search)"
    )
}

# Delay between HTTP requests to be polite to the server (seconds)
REQUEST_DELAY = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_page(url: str, session: requests.Session) -> BeautifulSoup | None:
    """Fetch a page and return a BeautifulSoup object, or None on failure."""
    try:
        response = session.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml")
    except requests.RequestException as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        return None


def get_atc_links(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Return a list of (href, text) tuples for ATC sub-level links found on
    the current page.  Links follow the pattern:
      /atc_ddd_index/?code=XXXXX
    """
    links = []
    for anchor in soup.select("a[href*='atc_ddd_index/?code=']"):
        href = anchor.get("href", "")
        text = anchor.get_text(strip=True)
        if href and text:
            full_url = BASE_URL + href if href.startswith("/") else href
            links.append((full_url, text))
    return links


def parse_ddd_table(soup: BeautifulSoup) -> list[dict]:
    """
    Parse the DDD data table on a leaf-level ATC page.

    The table has columns:
      ATC code | Name | DDD | U | Adm.R | Note
    Returns a list of dicts with keys:
      atc_code, drug_name, ddd_value, ddd_unit, adm_route, note
    """
    records = []
    table = soup.find("table", class_="atcdetails")
    if table is None:
        return records

    rows = table.find_all("tr")
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        atc_code = cols[0].get_text(strip=True)
        drug_name = cols[1].get_text(strip=True)
        ddd_value = cols[2].get_text(strip=True)
        ddd_unit = cols[3].get_text(strip=True)
        adm_route = cols[4].get_text(strip=True)
        note = cols[5].get_text(strip=True) if len(cols) > 5 else ""

        # Skip header-like rows or empty rows
        if not atc_code or atc_code.lower() == "atc code":
            continue

        records.append(
            {
                "atc_code": atc_code,
                "drug_name": drug_name,
                "ddd_value": ddd_value,
                "ddd_unit": ddd_unit,
                "adm_route": adm_route,
                "note": note,
            }
        )
    return records


def is_leaf_page(soup: BeautifulSoup) -> bool:
    """
    A leaf page contains the DDD details table (class='atcdetails').
    Non-leaf pages list sub-level ATC codes.
    """
    return soup.find("table", class_="atcdetails") is not None


def scrape_level(url: str, session: requests.Session, visited: set) -> list[dict]:
    """
    Recursively crawl the ATC hierarchy starting at *url*.
    Returns all DDD records found beneath this node.
    """
    if url in visited:
        return []
    visited.add(url)
    time.sleep(REQUEST_DELAY)

    soup = get_page(url, session)
    if soup is None:
        return []

    # If this is a leaf page, extract the DDD table
    if is_leaf_page(soup):
        records = parse_ddd_table(soup)
        logger.info("  -> %d record(s) at %s", len(records), url)
        return records

    # Otherwise, follow sub-level links
    sub_links = get_atc_links(soup)
    all_records: list[dict] = []
    for sub_url, link_text in sub_links:
        logger.info("Visiting: %s  (%s)", sub_url, link_text)
        all_records.extend(scrape_level(sub_url, session, visited))

    return all_records


def main() -> None:
    session = requests.Session()
    visited: set[str] = set()

    logger.info("Starting ATC/DDD scrape from %s", INDEX_URL)
    soup = get_page(INDEX_URL, session)
    if soup is None:
        logger.error("Could not fetch the index page. Exiting.")
        return

    top_links = get_atc_links(soup)
    logger.info("Found %d top-level ATC groups.", len(top_links))

    all_records: list[dict] = []
    for url, text in top_links:
        logger.info("Processing top-level group: %s  (%s)", text, url)
        all_records.extend(scrape_level(url, session, visited))

    if not all_records:
        logger.warning("No records were collected. The site may be unreachable.")
        return

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "atc_code",
            "drug_name",
            "ddd_value",
            "ddd_unit",
            "adm_route",
            "note",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    logger.info(
        "Done. %d record(s) written to %s", len(all_records), OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
