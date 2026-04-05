# =============================================================================
# STRAT-412: Sprouts Farmers Market Store Directory Scraper
# =============================================================================
# This script scrapes the entire Sprouts Farmers Market store directory
# from https://www.sprouts.com/stores/ and exports the data to a CSV file.
#
# The scraper navigates a 3-level hierarchy:
#   1. Main directory → State pages
#   2. State pages → City pages
#   3. City pages → Individual store pages
#
# Output CSV columns:
#   Store Name, Store Number, Store Complex, Address, City, State, Zip, Phone Number
#
# To run in Google Colab, paste each section (separated by banners) into
# its own code cell. Add markdown cells above each for descriptions.
# =============================================================================


# =============================================================================
# CELL 1: Imports & Setup
# =============================================================================
# Install required packages (uncomment if running in Google Colab)
# !pip install beautifulsoup4 lxml requests

import requests
from bs4 import BeautifulSoup
import csv
import time
import re

# Browser-like headers to avoid 403 Forbidden responses.
# The Sprouts website blocks requests that don't look like real browsers.
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Base URL for the Sprouts website
BASE_URL = "https://www.sprouts.com"


def get_soup(url):
    """
    Fetches a URL with browser-like headers and returns a BeautifulSoup object.
    Includes a 1-second delay between requests to be respectful to the server.
    """
    time.sleep(1)  # polite delay between requests
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # raise an error if the request failed
    return BeautifulSoup(response.text, "lxml")


# =============================================================================
# CELL 1.5 (Optional): Discovery / Inspect Raw HTML
# =============================================================================
# Uncomment the lines below to inspect the raw HTML of a store page.
# This helps identify the correct CSS selectors for extracting data.
#
# test_url = "https://www.sprouts.com/store/co/westminster/westminster/"
# soup = get_soup(test_url)
# print(soup.prettify()[:5000])  # print first 5000 characters of HTML


# =============================================================================
# CELL 2: CODE BLOCK #1 — Scrape Location Info for One Store
# =============================================================================
# This function extracts all required fields from a single store page.
# It looks for common HTML patterns used on store locator pages.

def scrape_one_store(url):
    """
    Scrapes a single Sprouts store page and returns a dictionary with:
    Store Name, Store Number, Store Complex, Address, City, State, Zip, Phone Number
    """
    soup = get_soup(url)

    # Initialize fields with defaults
    store_name = ""
    store_number = ""
    store_complex = ""
    address = ""
    city = ""
    state = ""
    zipcode = ""
    phone = ""

    # --- Store Name ---
    # The store name is typically in the page's <h1> tag or a prominent heading
    h1 = soup.find("h1")
    if h1:
        store_name = h1.get_text(strip=True)

    # --- Store Number ---
    # Look for "Store #" or "Store No." patterns in the page text
    page_text = soup.get_text()
    store_num_match = re.search(r'Store\s*#?\s*(\d+)', page_text)
    if store_num_match:
        store_number = store_num_match.group(1)

    # --- Address, City, State, Zip ---
    # Look for address information in common elements:
    # 1. <address> tag
    # 2. Elements with "address" in class name
    # 3. Schema.org structured data (JSON-LD)
    # 4. itemprop="address" attributes

    # Try JSON-LD structured data first (most reliable if present)
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            import json
            data = json.loads(script.string)
            # Handle both single object and array formats
            if isinstance(data, list):
                data = data[0]
            if "address" in data:
                addr = data["address"]
                address = addr.get("streetAddress", "")
                city = addr.get("addressLocality", "")
                state = addr.get("addressRegion", "")
                zipcode = addr.get("postalCode", "")
            if "telephone" in data:
                phone = data["telephone"]
            if "name" in data and not store_name:
                store_name = data["name"]
            # Look for store number in the structured data
            if "branchCode" in data and not store_number:
                store_number = data["branchCode"]
        except (json.JSONDecodeError, TypeError, KeyError):
            continue

    # Fallback: look for address in <address> tag or elements with address-related classes
    if not address:
        addr_tag = soup.find("address")
        if addr_tag:
            addr_text = addr_tag.get_text(separator=", ", strip=True)
            address = addr_text

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
        # Search for phone number pattern in page text
        phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', page_text)
        if phone_match:
            phone = phone_match.group(0)

    # --- Store Complex ---
    # The shopping center name may appear as a subtitle, in a specific class,
    # or near the address. Look for common patterns.
    # Try to find it in elements near the store name or address
    complex_el = (
        soup.find(class_=re.compile(r'complex|plaza|center|shopping', re.I))
        or soup.find(class_=re.compile(r'subtitle|subheading|sub-title', re.I))
    )
    if complex_el:
        store_complex = complex_el.get_text(strip=True)

    # Also check the page title or h2 elements for shopping center names
    if not store_complex:
        h2_tags = soup.find_all("h2")
        for h2 in h2_tags:
            text = h2.get_text(strip=True)
            # Shopping centers often have words like "Plaza", "Center", "Village", etc.
            if re.search(r'Plaza|Center|Village|Square|Mall|Shopping|Market|Commons', text, re.I):
                store_complex = text
                break

    # --- Data Cleaning ---
    # Ensure zip code is exactly 5 digits
    zip_match = re.search(r'\d{5}', zipcode)
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


# Test with one store
print("=" * 60)
print("SCRAPING ONE STORE")
print("=" * 60)
test_url = "https://www.sprouts.com/store/co/westminster/westminster/"
result = scrape_one_store(test_url)
for key, value in result.items():
    print(f"  {key}: {value}")


# =============================================================================
# CELL 3: CODE BLOCK #2 — Test with a Small Loop of 3-4 URLs
# =============================================================================
# Test the one-store scraping code on a few known store URLs to verify
# it works correctly across different states and page layouts.

test_urls = [
    "https://www.sprouts.com/store/co/westminster/westminster/",
    "https://www.sprouts.com/store/ga/atlanta/529-buford-i85-hwy20/",
    "https://www.sprouts.com/store/wa/seattle/seattle/",
    "https://www.sprouts.com/store/nj/cliffwood/hwy-35/",
]

print("=" * 60)
print("TESTING WITH SMALL LOOP (3-4 URLs)")
print("=" * 60)

test_results = []
for url in test_urls:
    print(f"\nScraping: {url}")
    try:
        store_data = scrape_one_store(url)
        test_results.append(store_data)
        for key, value in store_data.items():
            print(f"  {key}: {value}")
    except Exception as e:
        print(f"  ERROR: {e}")

print(f"\nSuccessfully scraped {len(test_results)} out of {len(test_urls)} test stores.")


# =============================================================================
# CELL 4: CODE BLOCK #3 — Print the List of State URLs
# =============================================================================
# Scrape the main store directory page to get all state URLs.
# State links follow the pattern: /stores/{state-abbreviation}/

print("=" * 60)
print("GETTING STATE URLs")
print("=" * 60)

soup = get_soup(f"{BASE_URL}/stores/")

# Find all links that match the state URL pattern: /stores/XX/
# State abbreviations are 2 lowercase letters
state_urls = []
for link in soup.find_all("a", href=True):
    href = link["href"]
    # Match pattern like /stores/az/ or /stores/ca/ (2-letter state codes)
    if re.match(r'^/stores/[a-z]{2}/?$', href):
        full_url = BASE_URL + href.rstrip("/") + "/"
        if full_url not in state_urls:
            state_urls.append(full_url)

# Sort alphabetically for readability
state_urls.sort()

print(f"Found {len(state_urls)} state URLs:\n")
for url in state_urls:
    print(f"  {url}")


# =============================================================================
# CELL 5: CODE BLOCK #4 — Print the List of City URLs
# =============================================================================
# For each state page, scrape the city-level links.
# City links follow the pattern: /stores/{state}/{city}/

print("=" * 60)
print("GETTING CITY URLs")
print("=" * 60)

city_urls = []

for state_url in state_urls:
    print(f"Scraping cities from: {state_url}")
    try:
        soup = get_soup(state_url)

        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Match city-level URLs: /stores/{state}/{city}/
            # State is 2 letters, city is one or more lowercase letters/hyphens
            if re.match(r'^/stores/[a-z]{2}/[\w-]+/?$', href):
                full_url = BASE_URL + href.rstrip("/") + "/"
                if full_url not in city_urls:
                    city_urls.append(full_url)
    except Exception as e:
        print(f"  ERROR scraping {state_url}: {e}")

city_urls.sort()

print(f"\nFound {len(city_urls)} city URLs:\n")
for url in city_urls:
    print(f"  {url}")


# =============================================================================
# CELL 6: CODE BLOCK #5 — Print the List of Store URLs
# =============================================================================
# For each city page, scrape the individual store page links.
# Store links follow the pattern: /store/{state}/{city}/{store-slug}/
# Note: individual stores use singular /store/ (not /stores/)

print("=" * 60)
print("GETTING STORE URLs")
print("=" * 60)

store_urls = []

# If no city URLs were found, try getting store URLs directly from state pages
urls_to_scrape = city_urls if city_urls else state_urls

for page_url in urls_to_scrape:
    print(f"Scraping store links from: {page_url}")
    try:
        soup = get_soup(page_url)

        for link in soup.find_all("a", href=True):
            href = link["href"]
            # Match individual store URLs: /store/{state}/{city}/{slug}/
            # Note the singular "store" (not "stores")
            if re.match(r'^/store/[a-z]{2}/[\w-]+/[\w-]+/?$', href):
                full_url = BASE_URL + href.rstrip("/") + "/"
                if full_url not in store_urls:
                    store_urls.append(full_url)
    except Exception as e:
        print(f"  ERROR scraping {page_url}: {e}")

# Also check state pages for direct store links (some states may list stores
# directly without an intermediate city page)
if city_urls:
    print("\nAlso checking state pages for direct store links...")
    for state_url in state_urls:
        try:
            soup = get_soup(state_url)
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if re.match(r'^/store/[a-z]{2}/[\w-]+/[\w-]+/?$', href):
                    full_url = BASE_URL + href.rstrip("/") + "/"
                    if full_url not in store_urls:
                        store_urls.append(full_url)
        except Exception as e:
            print(f"  ERROR scraping {state_url}: {e}")

store_urls.sort()

print(f"\nFound {len(store_urls)} store URLs:\n")
for url in store_urls:
    print(f"  {url}")


# =============================================================================
# CELL 7: CODE BLOCK #6 — Loop Through All Store URLs
# =============================================================================
# Scrape every individual store page and collect the data.
# Includes error handling and progress reporting.

print("=" * 60)
print("SCRAPING ALL STORES")
print("=" * 60)

all_stores = []
errors = []

total = len(store_urls)
for i, url in enumerate(store_urls, start=1):
    # Print progress every 25 stores
    if i % 25 == 0 or i == 1:
        print(f"  Progress: {i}/{total} stores scraped...")

    try:
        store_data = scrape_one_store(url)
        store_data["URL"] = url  # keep track of source URL for debugging
        all_stores.append(store_data)
    except Exception as e:
        print(f"  ERROR on {url}: {e}")
        errors.append({"url": url, "error": str(e)})

print(f"\nDone! Successfully scraped {len(all_stores)} stores.")
if errors:
    print(f"Encountered {len(errors)} errors:")
    for err in errors:
        print(f"  {err['url']}: {err['error']}")


# =============================================================================
# CELL 8: CODE BLOCK #7 — Write to CSV and Export
# =============================================================================
# Write the collected store data to a CSV file.

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

with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_stores)

print(f"CSV file '{csv_filename}' written with {len(all_stores)} rows.")
print(f"Columns: {', '.join(csv_columns)}")

# Preview the first 5 rows
print("\nPreview (first 5 rows):")
for store in all_stores[:5]:
    print(f"  {store['Store Name']} | #{store['Store Number']} | "
          f"{store['Address']}, {store['City']}, {store['State']} {store['Zip']} | "
          f"{store['Phone Number']}")

# Uncomment the lines below to auto-download the CSV in Google Colab:
# from google.colab import files
# files.download(csv_filename)
