# -*- coding: utf-8 -*-
"""
STRAT-412: Sprouts Farmers Market Store Directory Scraper

This notebook scrapes the entire Sprouts Farmers Market store directory
from the Sprouts website and exports the data to a CSV file.

The scraper navigates a 3-level hierarchy:
  1. Main directory -> State pages
  2. State pages -> City pages
  3. City pages -> Individual store pages

Output CSV columns:
  Store Name, Store Number, Store Complex, Address, City, State, Zip, Phone Number

Note: The Sprouts website blocks standard HTTP requests (403 Forbidden),
so we use cloudscraper to bypass anti-bot protection.

To run in Google Colab:
  1. Upload this file or open from GitHub
  2. Go to File > Open in Colab (or Runtime > Run all)
"""

# ==============================================================================
# CELL 1: IMPORTS AND SETUP
# ==============================================================================
# Install required packages (run this line in Colab)
# !pip install cloudscraper beautifulsoup4 lxml

import cloudscraper
from bs4 import BeautifulSoup
import csv
import json
import time
import re

# Base URL for the Sprouts website
BASE_URL = "https://www.sprouts.com"

# Create a cloudscraper session that handles Cloudflare/anti-bot automatically.
# This is simpler and more reliable than Selenium in Google Colab.
scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "desktop": True,
    }
)


def get_soup(url, wait_seconds=1.5):
    """
    Fetches a URL using cloudscraper (bypasses Cloudflare protection)
    and returns a BeautifulSoup object for parsing.
    Includes a polite delay between requests to avoid overwhelming the server.
    """
    time.sleep(wait_seconds)
    response = scraper.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


# Quick test to verify setup works
test_soup = get_soup(BASE_URL + "/stores/")
test_title = test_soup.find("title")
print("Page title:", test_title.get_text(strip=True) if test_title else "No title found")
print("Page length:", len(test_soup.get_text()), "characters")
print("Setup complete!")


# ==============================================================================
# CELL 2: DISCOVERY - INSPECT RAW HTML
# ==============================================================================
# Run this cell to see the raw HTML structure of a store page.
# This helps verify where store name, address, phone, etc. appear.

discovery_url = BASE_URL + "/store/co/westminster/westminster/"
discovery_soup = get_soup(discovery_url, wait_seconds=3)

print("=== FIRST 5000 CHARS ===")
print(discovery_soup.prettify()[:5000])

print("\n=== JSON-LD STRUCTURED DATA ===")
json_ld_scripts = discovery_soup.find_all("script", type="application/ld+json")
for i, script in enumerate(json_ld_scripts):
    try:
        data = json.loads(script.string)
        print("\nJSON-LD block " + str(i + 1) + ":")
        print(json.dumps(data, indent=2)[:2000])
    except Exception:
        print("Could not parse JSON-LD block " + str(i + 1))

print("\n=== H1 TAG ===")
h1 = discovery_soup.find("h1")
print(h1.get_text(strip=True) if h1 else "No h1 found")

print("\n=== ADDRESS ELEMENTS ===")
addr = discovery_soup.find("address")
print(addr.get_text(strip=True) if addr else "No address tag found")


# ==============================================================================
# CELL 3: CODE BLOCK #1 - SCRAPE LOCATION INFO FOR ONE STORE
# ==============================================================================
# This function extracts all 8 required fields from a single store page.
#
# Extraction strategy (in priority order):
#   1. JSON-LD structured data - most reliable
#   2. Schema.org microdata (itemprop attributes) - fallback
#   3. HTML elements (h1, address tags) - secondary fallback
#   4. Regex patterns - last resort for phone numbers and store numbers

def scrape_one_store(url):
    """
    Scrapes a single Sprouts store page and returns a dictionary with:
    Store Name, Store Number, Store Complex, Address, City, State, Zip, Phone Number
    """
    soup = get_soup(url)

    # Initialize all fields with empty defaults
    store_name = ""
    store_number = ""
    store_complex = ""
    address = ""
    city = ""
    state = ""
    zipcode = ""
    phone = ""

    # --- Store Name ---
    # The store name is typically in the page's h1 tag
    h1 = soup.find("h1")
    if h1:
        store_name = h1.get_text(strip=True)

    # --- Store Number ---
    # Look for "Store #" or "Store No." patterns in the page text
    page_text = soup.get_text()
    store_num_match = re.search(r"Store\s*#?\s*(\d+)", page_text)
    if store_num_match:
        store_number = store_num_match.group(1)

    # --- Address, City, State, Zip, Phone ---
    # Try JSON-LD structured data first (most reliable if present)
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            # Handle both single object and array formats
            if isinstance(data, list):
                data = data[0]
            # Extract address fields from JSON-LD
            if "address" in data:
                addr_data = data["address"]
                address = addr_data.get("streetAddress", "")
                city = addr_data.get("addressLocality", "")
                state = addr_data.get("addressRegion", "")
                zipcode = addr_data.get("postalCode", "")
            # Extract phone from JSON-LD
            if "telephone" in data:
                phone = data["telephone"]
            # Extract name from JSON-LD if not found in h1
            if "name" in data and not store_name:
                store_name = data["name"]
            # Some sites store branch/store number in branchCode
            if "branchCode" in data and not store_number:
                store_number = data["branchCode"]
        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    # Fallback: look for address in address tag
    if not address:
        addr_tag = soup.find("address")
        if addr_tag:
            address = addr_tag.get_text(separator=", ", strip=True)

    # Fallback: look for itemprop attributes (Schema.org microdata)
    if not address:
        street_el = soup.find(attrs={"itemprop": "streetAddress"})
        if street_el:
            address = street_el.get_text(strip=True)
    if not city:
        city_el = soup.find(attrs={"itemprop": "addressLocality"})
        if city_el:
            city = city_el.get_text(strip=True)
    if not state:
        state_el = soup.find(attrs={"itemprop": "addressRegion"})
        if state_el:
            state = state_el.get_text(strip=True)
    if not zipcode:
        zip_el = soup.find(attrs={"itemprop": "postalCode"})
        if zip_el:
            zipcode = zip_el.get_text(strip=True)

    # --- Phone Number ---
    if not phone:
        phone_el = soup.find(attrs={"itemprop": "telephone"})
        if phone_el:
            phone = phone_el.get_text(strip=True)
    if not phone:
        # Try finding a tel: link
        tel_link = soup.find("a", href=re.compile(r"^tel:"))
        if tel_link:
            phone = tel_link.get_text(strip=True)
    if not phone:
        # Regex fallback: search for phone number pattern in page text
        phone_match = re.search(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", page_text)
        if phone_match:
            phone = phone_match.group(0)

    # --- Store Complex ---
    # The shopping center/plaza name may appear as a subtitle or specific class
    complex_el = (
        soup.find(class_=re.compile(r"complex|plaza|center|shopping", re.I))
        or soup.find(class_=re.compile(r"subtitle|subheading|sub-title", re.I))
    )
    if complex_el:
        store_complex = complex_el.get_text(strip=True)

    # Also check h2 elements for shopping center names
    if not store_complex:
        h2_tags = soup.find_all("h2")
        for h2 in h2_tags:
            text = h2.get_text(strip=True)
            if re.search(r"Plaza|Center|Village|Square|Mall|Shopping|Market|Commons", text, re.I):
                store_complex = text
                break

    # --- Data Cleaning ---
    # Ensure zip code is exactly 5 digits (trim any +4 extension)
    zip_match = re.search(r"\d{5}", zipcode)
    if zip_match:
        zipcode = zip_match.group(0)

    # Ensure state is a 2-character uppercase abbreviation
    state = state.strip().upper()[:2]

    # Clean phone number
    phone = phone.strip()

    return {
        "Store Name": store_name,
        "Store Number": store_number,
        "Store Complex": store_complex,
        "Address": address,
        "City": city,
        "State": state,
        "Zip": zipcode,
        "Phone Number": phone,
    }


# Test with one store to verify the function works
print("=" * 60)
print("SCRAPING ONE STORE")
print("=" * 60)
one_store_url = BASE_URL + "/store/co/westminster/westminster/"
result = scrape_one_store(one_store_url)
for key, value in result.items():
    print("  " + key + ": " + value)


# ==============================================================================
# CELL 4: CODE BLOCK #2 - TEST WITH A SMALL LOOP OF 3-4 URLS
# ==============================================================================
# Testing the scrape function on a few known store URLs from different states
# to verify it works correctly across different page layouts before scaling up.

test_urls = [
    BASE_URL + "/store/co/westminster/westminster/",
    BASE_URL + "/store/ga/atlanta/529-buford-i85-hwy20/",
    BASE_URL + "/store/wa/seattle/seattle/",
    BASE_URL + "/store/nj/cliffwood/hwy-35/",
]

print("=" * 60)
print("TESTING WITH SMALL LOOP (4 URLs)")
print("=" * 60)

test_results = []
for url in test_urls:
    print("\nScraping: " + url)
    try:
        store_data = scrape_one_store(url)
        test_results.append(store_data)
        for key, value in store_data.items():
            print("  " + key + ": " + value)
    except Exception as e:
        print("  ERROR: " + str(e))

print("\nSuccessfully scraped " + str(len(test_results)) + " out of " + str(len(test_urls)) + " test stores.")


# ==============================================================================
# CELL 5: CODE BLOCK #3 - PRINT THE LIST OF STATE URLS
# ==============================================================================
# Scrape the main store directory page to find all state-level URLs.
# State links follow the pattern /stores/{state-abbreviation}/
# Includes a hardcoded fallback list of known Sprouts states.

print("=" * 60)
print("GETTING STATE URLs")
print("=" * 60)

# Fetch the main store directory page
stores_url = BASE_URL + "/stores/"
soup = get_soup(stores_url, wait_seconds=3)

# Find all links that match the state URL pattern: /stores/XX/
# State abbreviations are 2 lowercase letters
state_urls = []
for link in soup.find_all("a", href=True):
    href = link["href"]
    # Match relative URLs like /stores/az/
    if re.match(r"^/stores/[a-z]{2}/?$", href):
        full_url = BASE_URL + href.rstrip("/") + "/"
        if full_url not in state_urls:
            state_urls.append(full_url)
    # Also handle full URLs like https://www.sprouts.com/stores/az/
    elif re.match(r"^https?://www\.sprouts\.com/stores/[a-z]{2}/?$", href):
        full_url = href.rstrip("/") + "/"
        if full_url not in state_urls:
            state_urls.append(full_url)

# Fallback: if no state links found dynamically, use hardcoded list
if not state_urls:
    print("No state links found dynamically. Using hardcoded state list as fallback.")
    KNOWN_STATES = [
        "al", "az", "ca", "co", "de", "fl", "ga", "ks", "la", "md",
        "mo", "nv", "nj", "nm", "ny", "nc", "ok", "pa", "sc", "tn",
        "tx", "ut", "va", "wa",
    ]
    state_urls = [BASE_URL + "/stores/" + s + "/" for s in KNOWN_STATES]

# Sort alphabetically for readability
state_urls.sort()

print("Found " + str(len(state_urls)) + " state URLs:\n")
for url in state_urls:
    print("  " + url)


# ==============================================================================
# CELL 6: CODE BLOCK #4 - PRINT THE LIST OF CITY URLS
# ==============================================================================
# For each state page, scrape the city-level links.
# City links follow the pattern /stores/{state}/{city}/

print("=" * 60)
print("GETTING CITY URLs")
print("=" * 60)

city_urls = []

for state_url in state_urls:
    print("Scraping cities from: " + state_url)
    try:
        soup = get_soup(state_url)

        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Match relative city-level URLs: /stores/{state}/{city}/
            if re.match(r"^/stores/[a-z]{2}/[\w-]+/?$", href):
                full_url = BASE_URL + href.rstrip("/") + "/"
                if full_url not in city_urls:
                    city_urls.append(full_url)
            # Also handle full URLs
            elif re.match(r"^https?://www\.sprouts\.com/stores/[a-z]{2}/[\w-]+/?$", href):
                full_url = href.rstrip("/") + "/"
                if full_url not in city_urls:
                    city_urls.append(full_url)
    except Exception as e:
        print("  ERROR scraping " + state_url + ": " + str(e))

city_urls.sort()

print("\nFound " + str(len(city_urls)) + " city URLs:\n")
for url in city_urls:
    print("  " + url)


# ==============================================================================
# CELL 7: CODE BLOCK #5 - PRINT THE LIST OF STORE URLS
# ==============================================================================
# For each city page (or state page if no cities exist), scrape individual
# store page links. Store links use singular /store/ (not /stores/) with
# the pattern /store/{state}/{city}/{store-slug}/

print("=" * 60)
print("GETTING STORE URLs")
print("=" * 60)

store_urls = []


def extract_store_links(soup):
    """Helper to find all individual store links in a page."""
    found = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Match relative store URLs: /store/{state}/{city}/{slug}/
        if re.match(r"^/store/[a-z]{2}/[\w-]+/[\w-]+/?$", href):
            full_url = BASE_URL + href.rstrip("/") + "/"
            found.append(full_url)
        # Also handle full URLs
        elif re.match(r"^https?://www\.sprouts\.com/store/[a-z]{2}/[\w-]+/[\w-]+/?$", href):
            full_url = href.rstrip("/") + "/"
            found.append(full_url)
    return found


# If city URLs were found, scrape store links from each city page.
# Otherwise, scrape store links directly from state pages.
urls_to_scrape = city_urls if city_urls else state_urls

for page_url in urls_to_scrape:
    print("Scraping store links from: " + page_url)
    try:
        soup = get_soup(page_url)
        for found_url in extract_store_links(soup):
            if found_url not in store_urls:
                store_urls.append(found_url)
    except Exception as e:
        print("  ERROR scraping " + page_url + ": " + str(e))

# Also check state pages for direct store links (some states may list
# stores directly without an intermediate city page)
if city_urls:
    print("\nAlso checking state pages for direct store links...")
    for state_url in state_urls:
        try:
            soup = get_soup(state_url)
            for found_url in extract_store_links(soup):
                if found_url not in store_urls:
                    store_urls.append(found_url)
        except Exception as e:
            print("  ERROR scraping " + state_url + ": " + str(e))

store_urls.sort()

print("\nFound " + str(len(store_urls)) + " store URLs:\n")
for url in store_urls:
    print("  " + url)


# ==============================================================================
# CELL 8: CODE BLOCK #6 - LOOP THROUGH ALL STORE URLS
# ==============================================================================
# Scrape every individual store page and collect the data.
# This will take approximately 15-20 minutes (~487 stores x 1.5s delay).
# Progress is printed every 25 stores.

print("=" * 60)
print("SCRAPING ALL STORES")
print("=" * 60)

all_stores = []
errors = []

total = len(store_urls)
for i, url in enumerate(store_urls, start=1):
    # Print progress every 25 stores
    if i % 25 == 0 or i == 1:
        print("  Progress: " + str(i) + "/" + str(total) + " stores scraped...")

    try:
        store_data = scrape_one_store(url)
        store_data["URL"] = url  # keep track of source URL for debugging
        all_stores.append(store_data)
    except Exception as e:
        print("  ERROR on " + url + ": " + str(e))
        errors.append({"url": url, "error": str(e)})

print("\nDone! Successfully scraped " + str(len(all_stores)) + " stores.")
if errors:
    print("Encountered " + str(len(errors)) + " errors:")
    for err in errors:
        print("  " + err["url"] + ": " + err["error"])


# ==============================================================================
# CELL 9: CODE BLOCK #7 - WRITE TO CSV AND EXPORT
# ==============================================================================
# Write the collected store data to a CSV file and download it.

csv_filename = "sprouts_stores.csv"
csv_columns = [
    "Store Name",
    "Store Number",
    "Store Complex",
    "Address",
    "City",
    "State",
    "Zip",
    "Phone Number",
]

# Write all store data to CSV
with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_stores)

print("CSV file '" + csv_filename + "' written with " + str(len(all_stores)) + " rows.")
print("Columns: " + ", ".join(csv_columns))

# Preview the first 5 rows
print("\nPreview (first 5 rows):")
for store in all_stores[:5]:
    print("  " + store["Store Name"] + " | #" + store["Store Number"] + " | "
          + store["Address"] + ", " + store["City"] + ", " + store["State"] + " " + store["Zip"]
          + " | " + store["Phone Number"])

# Uncomment the two lines below to auto-download the CSV in Google Colab:
# from google.colab import files
# files.download(csv_filename)
