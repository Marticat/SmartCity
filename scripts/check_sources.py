"""Check six reviewed public source pages, without auto-approving changed facts.

Run: python -m scripts.check_sources
Only page hashes and presence checks are stored; full pages are not redistributed.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from backend.app.config import DATA_DIR, USER_AGENT
from backend.app.data import atomic_json

ALLOWED_HOSTS = {
    "nmrk.kz", "www.nmrk.kz", "astanaballet.com", "www.astanaballet.com",
    "astanaopera.kz", "www.astanaopera.kz", "visitastana.kz", "www.visitastana.kz",
    "visitnursultan.kz", "www.visitnursultan.kz",
}


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def checked_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in {None, 443}):
        raise ValueError("Source is outside reviewed HTTPS allowlist")
    return url


def check_record(client, record):
    url = checked_url(record["source_url"])
    # Explicit redirect validation keeps this batch utility off arbitrary/internal URLs.
    for _ in range(4):
        response = client.get(url)
        if response.is_redirect:
            url = checked_url(urljoin(url, response.headers["location"]))
            continue
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError("Expected HTML source")
        if len(response.content) > 3_000_000:
            raise ValueError("Source page exceeds size limit")
        parser = TextOnly()
        parser.feed(response.text)
        text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
        missing = [term for term in record["check_terms"] if term.casefold() not in text.casefold()]
        return {
            "poi_id": record["poi_id"], "source_url": url,
            "status": "review_needed" if missing else "page_reachable_terms_present",
            "missing_terms": missing, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "reviewed_at_unchanged": record["reviewed_at"],
        }
    raise ValueError("Too many source redirects")


def main(output):
    bundle = json.loads((DATA_DIR / "enrichment" / "official-pois.json").read_text(encoding="utf-8"))
    results = []
    with httpx.Client(timeout=12, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
        for record in bundle["records"]:
            try:
                results.append(check_record(client, record))
            except (httpx.HTTPError, ValueError, KeyError):
                results.append({
                    "poi_id": record["poi_id"], "source_url": record["source_url"],
                    "status": "unavailable_review_needed",
                })
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reachability/change signal only. This does not verify every claim or renew the source review.",
        "results": results,
    }
    atomic_json(Path(output), report)
    print(json.dumps({"checked": len(results), "review_needed": sum(r["status"] != "page_reachable_terms_present" for r in results), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/manifests/source-check.json")
    main(parser.parse_args().output)
