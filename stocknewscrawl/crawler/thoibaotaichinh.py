"""
Crawler for thoibaotaichinhvietnam.vn
Target sections:
  - Tài chính   : /tai-chinh
  - Đầu tư     : /dau-tu
  - Chứng khoán : /chung-khoan
  - Thị trường  : /thi-truong

Pagination mechanism: AJAX "Xem thêm" button.
  API endpoint: POST or GET to apicenter@ path.
  For simplicity, the first page HTML gives initial articles via <a class="article-link">.
  Subsequent pages use offset-based API calls, but since extracting `last_id` is needed,
  we use a different strategy: scrape the initial page then use requests-based pagination
  via ?page=N (fallback) or detect the actual API pattern.

Strategy used here:
  - Page 1: Parse HTML directly, extract <a class="article-link"> hrefs
  - Page 2+: Try common CMS pagination patterns (?page=N, /page/N)
  - If pagination fails (no articles), stop early
"""

import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from crawler.base_crawler import BaseCrawler


class ThoiBaoTaiChinhCrawler(BaseCrawler):

    BASE_URL = "https://thoibaotaichinhvietnam.vn"

    CATEGORY_MAP = {
        "tai-chinh":   ("tai-chinh",   "Tài chính"),
        "dau-tu":      ("dau-tu",      "Đầu tư"),
        "chung-khoan": ("chung-khoan", "Chứng khoán"),
        "thi-truong":  ("thi-truong",  "Thị trường"),
    }

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)

    def get_categories(self) -> dict:
        return {slug: info[1] for slug, info in self.CATEGORY_MAP.items()}

    def get_urls_of_category_page(self, category_slug: str, page_number: int) -> list:
        """
        Fetch article URLs from a category page.
        Tries multiple pagination URL patterns.
        Article links have class="article-link".
        """
        path = self.CATEGORY_MAP[category_slug][0]
        base_cat_url = f"{self.BASE_URL}/{path}"

        # Try different pagination patterns
        if page_number == 1:
            candidates = [base_cat_url]
        else:
            candidates = [
                f"{base_cat_url}?page={page_number}",
                f"{base_cat_url}/page/{page_number}",
                f"{base_cat_url}?p={page_number}",
            ]

        for page_url in candidates:
            try:
                resp = requests.get(page_url, timeout=15,
                                    headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code != 200:
                    continue
            except Exception as e:
                self.logger.warning(f"[thoibao] Failed to fetch {page_url}: {e}")
                continue

            soup = BeautifulSoup(resp.content, "html.parser")

            # Primary: <a class="article-link">
            link_tags = soup.select("a.article-link")

            # Fallback: look for links inside article/news card containers
            if not link_tags:
                link_tags = soup.select(".article-title a, .news-title a, h3 a, h2 a")

            urls = []
            seen = set()
            for tag in link_tags:
                href = tag.get("href", "").strip()
                if not href or href in seen:
                    continue
                # Only keep article-looking URLs (contain .html or have slug pattern)
                if ".html" not in href and href.count("-") < 2:
                    continue
                full_url = href if href.startswith("http") else self.BASE_URL + "/" + href.lstrip("/")
                if full_url not in seen:
                    urls.append(full_url)
                    seen.add(full_url)

            if urls:
                return urls
            # If this candidate gave no results, try next pattern

        self.logger.info(f"[thoibao] No articles found for {category_slug} page {page_number}")
        return []
