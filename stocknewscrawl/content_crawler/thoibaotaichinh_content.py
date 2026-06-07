"""Content crawler for thoibaotaichinhvietnam.vn"""
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from content_crawler.base_content_crawler import BaseContentCrawler
from content_crawler.content_utils import extract_best_content, parse_datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SOURCE_NAME = "Thời Báo Tài Chính Việt Nam"


class ThoiBaoTaiChinhContentCrawler(BaseContentCrawler):

    def extract_article(self, url: str) -> dict | None:
        try:
            resp = requests.get(url, timeout=15, headers=HEADERS)
            resp.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(resp.content, "html.parser")

        # --- Title ---
        # NOTE: <h1> on this site is the CATEGORY name, NOT the article title
        # Use og:title first, then .post-title (h2)
        title = ""
        og = soup.find("meta", property="og:title")
        if og:
            title = og.get("content", "").strip()
        if not title:
            t = soup.find(class_="post-title") or soup.find("h2", class_="title")
            title = t.get_text(strip=True) if t else ""
        if not title:
            return None

        # --- Summary ---
        summary = ""
        og_desc = soup.find("meta", property="og:description") or soup.find("meta", {"name": "description"})
        if og_desc:
            summary = og_desc.get("content", "").strip()
        if not summary:
            s = soup.find(class_="post-sapo") or soup.find("p", class_="sapo")
            summary = s.get_text(strip=True) if s else ""

        # --- Image ---
        image_url = ""
        og_img = soup.find("meta", property="og:image")
        if og_img:
            image_url = og_img.get("content", "")

        # --- Date ---
        # QUAN TRỌNG: đọc date TRƯỚC extract_best_content (mutate in-place).
        # Site này KHÔNG có meta article:published_time; ngày nằm ở
        # <span class="format_date">14/04/2026</span> + <span class="format_time">22:07</span>.
        pub_at, pub_date = "", ""
        meta_date = soup.find("meta", property="article:published_time")
        if meta_date and meta_date.get("content"):
            pub_at, pub_date = parse_datetime(meta_date["content"])
        if not pub_at:
            d_el = soup.find(class_="format_date")
            t_el = soup.find(class_="format_time")
            if d_el:
                raw = d_el.get_text(strip=True)
                if t_el:
                    raw = f"{t_el.get_text(strip=True)} {raw}"  # "22:07 14/04/2026"
                pub_at, pub_date = parse_datetime(raw)
        if not pub_at:
            dt = soup.find(class_="post-time") or soup.find(class_="article-date") or soup.find("time")
            if dt:
                raw = dt.get("datetime", "") or dt.get_text(strip=True)
                pub_at, pub_date = parse_datetime(raw)

        # --- Content --- (gọi CUỐI vì mutate soup in-place)
        content = extract_best_content(soup)

        return {
            "title": title,
            "summary": summary,
            "content": content,
            "image_url": image_url,
            "published_at": pub_at,
            "published_date": pub_date,
            "source": SOURCE_NAME,
        }
