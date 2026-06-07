"""
Shared content extraction utilities + date/dedup checks.

Chiến lược lấy toàn bộ nội dung bài báo:
  - XÓA noise tags (nav/footer/aside/figure/script) ra khỏi soup IN-PLACE
    (meta tags đã được đọc bởi parser trước khi gọi hàm này)
  - Thu thập TẤT CẢ <p> còn lại → đảm bảo không bỏ sót khi ảnh ngăn cách đoạn văn

QUAN TRỌNG: Gọi hàm này SAU KHI đã đọc xong title/summary/image/date từ soup,
vì hàm sẽ modify soup in-place (xoá noise elements).
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

_HEADERS_PROBE = {"User-Agent": "Mozilla/5.0 (probe-date)"}


# ─────────────────────────────────────────────────────────
# Noise patterns
# ─────────────────────────────────────────────────────────

NOISE_TAGS = [
    "nav", "header", "footer", "aside",
    "script", "style", "noscript", "iframe",
    "form", "button", "select", "figure",
]

# Matches class/id strings that indicate noise
NOISE_CLASS_RE = re.compile(
    r"\b(menu|breadcrumb|sidebar|related|suggest|recommen|"
    r"comment|discuss|social|share|ads|advert|promo|banner|"
    r"copyright|paginat|pager|author-info|writer-info)\b",
    re.I
)


def _is_noise_el(el) -> bool:
    classes = " ".join(el.get("class", []))
    el_id = el.get("id", "")
    return bool(NOISE_CLASS_RE.search(f"{classes} {el_id}"))


def extract_best_content(soup) -> str:
    """
    Parse nội dung bài báo từ soup.
    
    Quy trình:
      1. Xóa NOISE tags (nav, footer, aside, figure, script…) trực tiếp từ soup
         → an toàn vì meta tags (og:title, og:image…) nằm trong <head>, không bị xoá
      2. Xóa elements có class/id noise (sidebar, comment, share…)
         → dùng list() để tránh lỗi khi iterate + decompose
      3. Thu thập TẤT CẢ <p> còn lại trong body
         → ảnh (<img>) không phải <p> nên không bao giờ bị bỏ sót
      4. Lọc đoạn quá ngắn / spam / footer text
    """
    # Bước 1: Xoá noise tags (an toàn - không động vào <head>)
    for tag_name in NOISE_TAGS:
        for el in list(soup.find_all(tag_name)):  # list() để snapshots trước khi xoá
            el.decompose()

    # Bước 2: Xoá elements theo class/id noise
    for el in list(soup.find_all(True)):          # list() — critical!
        try:
            if _is_noise_el(el):
                el.decompose()
        except Exception:
            pass  # skip nếu element đã bị xoá bởi parent decompose

    # Bước 3: Lấy tất cả <p> còn lại
    paragraphs = []
    for p in soup.find_all("p"):
        try:
            text = p.get_text(separator=" ", strip=True)
            if _is_valid_paragraph(text):
                paragraphs.append(text)
        except Exception:
            pass

    return "\n".join(paragraphs)


def _is_valid_paragraph(text: str) -> bool:
    """True nếu là đoạn nội dung bài thật, không phải noise."""
    if not text or len(text) < 30:
        return False
    if text.startswith(("http://", "https://", "www.")):
        return False
    if re.match(r"^\[.+\]$", text):
        return False
    FOOTER_KEYWORDS = [
        "©", "bản quyền", "tòa soạn", "giấy phép",
        "tổng biên tập", "phó tổng biên tập",
        "điện thoại:", "email:", "fax:",
        "onecms", "mastercms", "issn",
    ]
    text_lower = text.lower()
    if any(kw in text_lower for kw in FOOTER_KEYWORDS):
        return False
    return True


# ─────────────────────────────────────────────────────────
# Datetime parser
# ─────────────────────────────────────────────────────────

def parse_datetime(raw: str) -> tuple:
    """Parse nhiều định dạng ngày tháng → (ISO timestamp, YYYY-MM-DD)."""
    if not raw:
        return "", ""
    raw = raw.strip().replace(" | ", " ").replace("|", " ")
    FORMATS = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y - %H:%M",
        "%H:%M %d/%m/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%m/%d/%Y %I:%M:%S %p",   # US: "4/14/2026 5:02:01 PM"
        "%m/%d/%Y %H:%M:%S",
    ]
    for fmt in FORMATS:
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S"), dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        d = m.group(1)
        return d + "T00:00:00", d
    m2 = re.search(r"(\d{2}/\d{2}/\d{4})", raw)
    if m2:
        try:
            dt = datetime.strptime(m2.group(1), "%d/%m/%Y")
            return dt.strftime("%Y-%m-%dT00:00:00"), dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return "", ""


# ─────────────────────────────────────────────────────────
# Date + dedup helpers (dùng chung cho URL crawler & content crawler)
# ─────────────────────────────────────────────────────────

def probe_article_date(url: str, timeout: int = 10) -> str:
    """
    Tải nhanh trang bài viết và parse ngày đăng (YYYY-MM-DD).
    Trả về "" nếu không xác định được.
    Hỗ trợ các meta tag phổ biến + thẻ <time>.
    """
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS_PROBE)
        if resp.status_code != 200:
            return ""
    except Exception:
        return ""

    soup = BeautifulSoup(resp.content, "html.parser")

    for selector in [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"itemprop": "datePublished"}),
        ("meta", {"name": "DC.date.issued"}),
    ]:
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            _, d = parse_datetime(tag["content"])
            if d:
                return d

    t = soup.find("time")
    if t:
        raw = t.get("datetime") or t.get_text(strip=True)
        _, d = parse_datetime(raw)
        if d:
            return d

    # post-time = baodautu.vn ("- 14/04/2026 21:04"); format_date = thoibaotaichinh ("14/04/2026")
    for cls in ["story__time", "post-time", "format_date", "time", "post-date", "date", "tbts-date"]:
        el = soup.find(class_=cls)
        if el:
            _, d = parse_datetime(el.get_text(strip=True))
            if d:
                return d
    return ""


def check_article(url: str,
                  published_date: str,
                  done_urls: set,
                  start_date: str,
                  end_date: str = "") -> tuple:
    """
    Hàm check thời gian + bài đã có (gộp 1 chỗ).

    Trả về (ok: bool, reason: str):
      - ok=True  → bài được giữ
      - ok=False → bỏ qua, kèm lý do: "duplicate" | "too_old" | "too_new"

    Quy tắc:
      - Nếu url đã có trong done_urls → "duplicate"
      - Nếu start_date != "" và published_date < start_date → "too_old"
      - Nếu end_date   != "" và published_date > end_date   → "too_new"
      - Thiếu published_date → vẫn cho qua (nhượng bộ, không loại oan)
    """
    if url in done_urls:
        return False, "duplicate"

    pub = (published_date or "").strip()[:10]
    if not pub:
        return True, "no_date"

    if start_date and pub < start_date:
        return False, "too_old"
    if end_date and pub > end_date:
        return False, "too_new"
    return True, "ok"
