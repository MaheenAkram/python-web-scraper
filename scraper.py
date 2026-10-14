"""Fetch one public HTML page and extract real, deduplicated records."""

from datetime import datetime, timezone
import json
from urllib.parse import urldefrag, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


class ScrapeError(ValueError):
    """A friendly error that can be displayed directly in the GUI."""


def clean_text(value):
    return " ".join(str(value if value is not None else "").split())


def validate_url(url):
    url = str(url).strip()
    if not url or any(character.isspace() for character in url):
        raise ScrapeError("Enter a complete HTTP or HTTPS URL without spaces.")
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
            raise ValueError
        if parts.username is not None or parts.password is not None:
            raise ValueError
        # Reading .port also validates malformed port numbers.
        parts.port
    except ValueError as exc:
        raise ScrapeError(
            "Invalid URL. Use a public address such as "
            "https://books.toscrape.com/ without embedded credentials."
        ) from exc
    return urldefrag(url)[0]


def safe_source(base_url, candidate=None):
    try:
        return validate_url(urljoin(base_url, str(candidate or "")))
    except ScrapeError:
        return base_url


def select_elements(node, selector):
    """BeautifulSoup supports CSS selectors through its bundled dependency."""
    try:
        return node.select(selector)
    except Exception as exc:
        raise ScrapeError(
            f"Invalid CSS selector: {selector!r}. Check its syntax and try again."
        ) from exc


def first_element(node, selector):
    matches = select_elements(node, selector)
    return matches[0] if matches else None


def element_text(node, prefer_title=False):
    if node is None:
        return ""
    if prefer_title and node.get("title"):
        return clean_text(node.get("title"))
    return clean_text(
        node.get("content")
        or node.get("data-price")
        or node.get_text(" ", strip=True)
        or node.get("alt")
        or node.get("title")
        or node.get("value")
    )


def element_link(node, base_url, selector=""):
    if selector:
        anchor = first_element(node, selector)
    elif node.name == "a" and node.get("href"):
        anchor = node
    else:
        anchor = node.find("a", href=True)
        if anchor is None:
            anchor = node.find_parent("a", href=True)
    if anchor is None:
        return base_url
    return safe_source(base_url, anchor.get("href") or anchor.get("content"))


def walk_json(value):
    """Visit nested JSON-LD objects, including @graph and product lists."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def structured_objects(soup):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, ValueError):
            continue
        yield from walk_json(data)


def has_schema_type(item, accepted):
    types = item.get("@type", [])
    if not isinstance(types, list):
        types = [types]
    return any(
        str(value).rstrip("/").split("/")[-1].lower() in accepted
        for value in types
    )


def structured_price(product):
    offers = product.get("offers", {})
    if not isinstance(offers, list):
        offers = [offers]
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        specification = offer.get("priceSpecification", {})
        if not isinstance(specification, dict):
            specification = {}
        price = offer.get("price")
        if price is None:
            price = offer.get("lowPrice")
        if price is None:
            price = specification.get("price")
        if price is not None and not isinstance(price, (list, dict)):
            currency = offer.get("priceCurrency") or specification.get("priceCurrency", "")
            return clean_text(f"{currency} {price}"), offer.get("url")
    return "", None


def fetch_page(url):
    try:
        with requests.Session() as session:
            session.max_redirects = 5
            session.headers.update({
                "User-Agent": (
                    "WebScraperDesktop/1.0 "
                    "(Python Requests; public-page data collection)"
                ),
                "Accept": "text/html,application/xhtml+xml",
            })
            response = session.get(url, timeout=(7, 25))

            if response.status_code in (401, 403):
                raise ScrapeError(
                    "The website denied access (401/403). It may require a login "
                    "or block automated requests. Do not bypass its restrictions."
                )
            if response.status_code == 429:
                raise ScrapeError(
                    "The website is rate-limiting requests (429). "
                    "Wait before trying again and respect the site's limits."
                )
            response.raise_for_status()
    except requests.Timeout as exc:
        raise ScrapeError(
            "The request timed out. Check your connection and try again later."
        ) from exc
    except requests.TooManyRedirects as exc:
        raise ScrapeError(
            "The website redirected too many times. Check the URL."
        ) from exc
    except requests.exceptions.SSLError as exc:
        raise ScrapeError(
            "The website's secure connection could not be verified. "
            "Check your computer's date and the website's certificate."
        ) from exc
    except requests.ConnectionError as exc:
        raise ScrapeError(
            "Could not connect. Check your internet connection and website address."
        ) from exc
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "unknown"
        raise ScrapeError(
            f"The website returned HTTP {code}. Check the page address and access."
        ) from exc
    except requests.RequestException as exc:
        raise ScrapeError(f"The request failed: {exc}") from exc

    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "html" not in content_type:
        raise ScrapeError(
            "This address did not return an HTML page. Use a website page, "
            "not a PDF, image, or API endpoint."
        )
    if len(response.content) > 12 * 1024 * 1024:
        raise ScrapeError("This page is larger than 12 MB. Try a smaller page.")

    # Parse bytes so BeautifulSoup can respect the HTML character encoding.
    soup = BeautifulSoup(response.content, "html.parser")
    title = element_text(soup.title).lower()
    if any(marker in title for marker in (
        "just a moment", "access denied", "attention required", "verify you are human"
    )):
        raise ScrapeError(
            "The website returned an access challenge instead of usable content. "
            "This app does not bypass CAPTCHAs or anti-bot protection."
        )
    return soup, validate_url(response.url)


def scrape_website(
    url,
    mode="Product Prices",
    item_selector="",
    text_selector="",
    value_selector="",
    link_selector="",
):
    """
    Return a list of dictionaries with the same four keys in every mode.

    Each call reads one page only. No browser execution, pagination,
    login handling, or automatic retry is performed.
    """
    url = validate_url(url)
    modes = ("Product Prices", "News Headlines", "Custom Data")
    if mode not in modes:
        raise ScrapeError("Choose Product Prices, News Headlines, or Custom Data.")

    selectors = [item_selector, text_selector, value_selector, link_selector]
    item_selector, text_selector, value_selector, link_selector = [
        str(selector or "").strip() for selector in selectors
    ]
    if mode == "Custom Data" and not item_selector:
        raise ScrapeError("Custom Data requires an item / container CSS selector.")
    if not item_selector and any((text_selector, value_selector, link_selector)):
        raise ScrapeError(
            "Provide an item / container selector when using relative selectors."
        )

    # Validate selector syntax before making a network request.
    empty_soup = BeautifulSoup("", "html.parser")
    for selector in (item_selector, text_selector, value_selector, link_selector):
        if selector:
            select_elements(empty_soup, selector)

    soup, page_url = fetch_page(url)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records = []
    seen = set()

    def add_record(text, value="", source=None):
        text = clean_text(text)
        value = clean_text(value)
        if not text:
            return
        source_url = safe_source(page_url, source)
        key = (text.casefold(), value, source_url)
        if key in seen:
            return
        seen.add(key)
        records.append({
            "text": text,
            "value": value,
            "source_url": source_url,
            "scraped_at": timestamp,
        })

    if item_selector:
        for item in select_elements(soup, item_selector):
            text_node = first_element(item, text_selector) if text_selector else item
            value_node = first_element(item, value_selector) if value_selector else None
            add_record(
                element_text(text_node, prefer_title=True),
                element_text(value_node),
                element_link(item, page_url, link_selector),
            )

    elif mode == "Product Prices":
        # First try structured metadata. Prices are never invented.
        for product in structured_objects(soup):
            if not has_schema_type(product, {"product"}):
                continue
            name = product.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            value, offer_url = structured_price(product)
            product_url = product.get("url")
            if not isinstance(product_url, str):
                product_url = None
            add_record(name, value, product_url or offer_url)

        # Different sites need different selectors. Use the first family
        # that yields records to avoid duplicating structured/card results.
        if not records:
            container_selectors = [
                '[itemscope][itemtype$="/Product"]',
                "article.product_pod",
                ".product-item",
                ".product-card",
                ".product",
                "[data-product-id]",
            ]
            for container_selector in container_selectors:
                for item in select_elements(soup, container_selector):
                    name_node = first_element(
                        item,
                        '[itemprop="name"], .product-title, .product-name, '
                        "h3 a, h2 a, h3, h2",
                    )
                    if name_node is None:
                        continue
                    price_node = first_element(
                        item,
                        '[itemprop="price"], .price_color, .product-price, '
                        ".price, [data-price]",
                    )
                    price = element_text(price_node)
                    currency = element_text(
                        first_element(item, '[itemprop="priceCurrency"]')
                    )
                    if price and currency and currency not in price:
                        price = f"{currency} {price}"
                    link = element_link(
                        item, page_url,
                        '[itemprop="url"][href], h3 a[href], h2 a[href], a[href]',
                    )
                    add_record(
                        element_text(name_node, prefer_title=True), price, link
                    )
                if records:
                    break

    elif mode == "News Headlines":
        for article in structured_objects(soup):
            if not has_schema_type(
                article, {"newsarticle", "article", "reportagenewsarticle"}
            ):
                continue
            headline = article.get("headline")
            if isinstance(headline, str) and headline.strip():
                source = article.get("url")
                if not isinstance(source, str):
                    source = page_url
                add_record(headline, source=source)

        if not records:
            headlines = select_elements(
                soup,
                'article h1, article h2, article h3, main h1, main h2, '
                'main h3, [itemprop="headline"], .entry-title, '
                ".post-title, .headline",
            )
            fallback = not headlines
            if fallback:
                headlines = select_elements(soup, "h1, h2, h3")
            for heading in headlines:
                if heading.find_parent(["nav", "footer", "aside"]):
                    continue
                link = element_link(heading, page_url)
                # Broad fallback headings must have a source link.
                if fallback and link == page_url:
                    continue
                add_record(element_text(heading, prefer_title=True), source=link)

    if not records:
        raise ScrapeError(
            "No matching records were found. Try CSS selectors suited to this "
            "website. It may load content with JavaScript; Requests and "
            "BeautifulSoup only parse returned HTML and do not run JavaScript."
        )
    return records
