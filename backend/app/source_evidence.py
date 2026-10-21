"""Bounded public-page text retrieval for short quoted evidence, without browser credentials."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from .data_utils import safe_url


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        for key, value in attrs:
            if key in ('datetime', 'content') and value and re.search(r'20\d{2}-\d{2}-\d{2}', value):
                self.parts.append(value)
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def public_page_url(url):
    if not safe_url(url):
        return False
    try:
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.port not in (None, 443):
            return False
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(row[4][0]).is_global for row in addresses)
    except (OSError, ValueError):
        return False


def fetch_page(source):
    original = source['url']
    parts = urlsplit(original)
    # Issuer press releases often cite the PDF presentation of the same HTML page.
    query = [(key, value) for key, value in parse_qsl(parts.query) if key.lower() != 'aspdf']
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))
    try:
        # Every redirect destination is checked; never follow a citation into a private service.
        with httpx.Client(timeout=6, follow_redirects=False, trust_env=False,
                          headers={'User-Agent': 'InvestIQ research source verification'}) as client:
            for _ in range(4):
                if not public_page_url(url):
                    return None
                with client.stream('GET', url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get('location', ''))
                        continue
                    response.raise_for_status()
                    if 'text/html' not in response.headers.get('content-type', ''):
                        return None
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 750_000:
                            return None
                    parser = PageText()
                    parser.feed(body.decode(response.encoding or 'utf-8', errors='replace'))
                    text = re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()
                    return {'url': original, 'title': source['title'], 'text': text[:24000]} if len(text) >= 100 else None
    except (httpx.HTTPError, OSError, ValueError):
        return None
    return None


def fetch_source_documents(sources):
    with ThreadPoolExecutor(max_workers=3) as pool:
        return [item for item in pool.map(fetch_page, sources[:5]) if item]
