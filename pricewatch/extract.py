"""Pull a product's current price out of its public product page.

Most store sites publish the price as schema.org data (JSON-LD or microdata) or
as Open Graph meta tags, so one generic extractor covers many of them. Sites that
block automated requests, or render prices only in the browser, return None and
those items fall back to manual entry.
"""
import json
import re
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)
META_RE = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\']'
    r'(?:product:price:amount|og:price:amount|price)["\'][^>]*>',
    re.I,
)
CONTENT_RE = re.compile(r'content=["\']([^"\']+)["\']', re.I)
ITEMPROP_RE = re.compile(r'itemprop=["\']price["\'][^>]*content=["\']([\d.,]+)["\']', re.I)


class FetchError(Exception):
    pass


def fetch_html(url, timeout=20):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except Exception as e:  # HTTPError, URLError, timeouts
        raise FetchError(str(e)) from e


def _to_price(value):
    if value is None:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    if not m:
        return None
    try:
        price = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    return price if price > 0 else None


def _walk(node):
    """Yield every dict nested anywhere in a JSON-LD document."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _price_from_offers(offers):
    for offer in offers if isinstance(offers, list) else [offers]:
        if not isinstance(offer, dict):
            continue
        for key in ("price", "lowPrice"):
            p = _to_price(offer.get(key))
            if p:
                return p
        spec = offer.get("priceSpecification")
        for s in spec if isinstance(spec, list) else [spec]:
            if isinstance(s, dict):
                p = _to_price(s.get("price"))
                if p:
                    return p
    return None


def price_from_jsonld(html):
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        for node in _walk(data):
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" in types and "offers" in node:
                p = _price_from_offers(node["offers"])
                if p:
                    return p
    return None


def price_from_meta(html):
    for tag in META_RE.findall(html):
        m = CONTENT_RE.search(tag)
        if m:
            p = _to_price(m.group(1))
            if p:
                return p
    m = ITEMPROP_RE.search(html)
    return _to_price(m.group(1)) if m else None


def extract_price(html):
    return price_from_jsonld(html) or price_from_meta(html)


def fetch_price(url):
    """Return the price found on the page, or None if the page has no readable price."""
    return extract_price(fetch_html(url))
