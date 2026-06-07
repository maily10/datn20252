"""Diagnose exactly why 393 URLs fail."""
import sys
sys.path.append('.')

# Test 1: Check if copy.copy on BeautifulSoup works
print("=== TEST 1: copy.copy behaviour ===")
from bs4 import BeautifulSoup
import copy

html = "<body><nav>menu</nav><p>Paragraph one is quite long enough to qualify</p></body>"
soup = BeautifulSoup(html, "html.parser")
body = soup.find("body")
working = copy.copy(body)
print(f"copy.copy type: {type(working)}")
print(f"Has find_all: {hasattr(working, 'find_all')}")
try:
    navs = working.find_all("nav")
    print(f"find_all('nav') OK, found {len(navs)}")
    if navs:
        navs[0].decompose()
    print(f"decompose() OK")
    paras = working.find_all("p")
    print(f"find_all('p') after decompose: {len(paras)} paragraphs")
    # Check if original was affected
    original_navs = body.find_all("nav")
    print(f"Original body nav count after copy decompose: {len(original_navs)}")
except Exception as e:
    print(f"ERROR: {e}")

# Test 2: Check share/social regex on article containers  
print("\n=== TEST 2: Noise filter false positives ===")
import re
NOISE_CLASS_PATTERNS = [
    r"\bshare\b", r"\bsocial\b", r"\btag\b",
]
_re = [re.compile(p, re.I) for p in NOISE_CLASS_PATTERNS]

# Classes that might appear on article body containers  
TEST_CLASSES = [
    "detail-content",
    "post-content", 
    "article-content",
    "story__content",
    "content-detail",
    "article-share",   # this SHOULD be noise
    "share-buttons",   # this SHOULD be noise
]
for cls in TEST_CLASSES:
    is_noise = any(pat.search(cls) for pat in _re)
    print(f"  '{cls}' → noise={is_noise}")

# Test 3: Actually test extract_best_content
print("\n=== TEST 3: extract_best_content on real URL ===")
from content_crawler.content_utils import extract_best_content
import requests
from bs4 import BeautifulSoup

url = "https://thoibaotaichinhvietnam.vn/quang-ninh-xu-ly-hon-1100-vu-buon-lau-gian-lan-thuong-mai-va-hang-gia-195658.html"
HEADERS = {"User-Agent": "Mozilla/5.0"}
try:
    resp = requests.get(url, timeout=15, headers=HEADERS)
    soup = BeautifulSoup(resp.content, "html.parser")
    content = extract_best_content(soup)
    print(f"Content length: {len(content)} chars")
    print(f"First 300 chars:\n{content[:300]}")
except Exception as e:
    print(f"ERROR: {e}")
