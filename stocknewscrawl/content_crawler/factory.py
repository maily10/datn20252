"""
Factory: auto-select content crawler based on URL domain.
"""
from urllib.parse import urlparse

from content_crawler.vneconomy_content import VnEconomyContentCrawler
from content_crawler.baodautu_content import BaoDauTuContentCrawler
from content_crawler.thoibaotaichinh_content import ThoiBaoTaiChinhContentCrawler
from content_crawler.thitruongtaichinh_content import ThiTruongContentCrawler

DOMAIN_MAP = {
    "vneconomy.vn":                VnEconomyContentCrawler,
    "baodautu.vn":                 BaoDauTuContentCrawler,
    "thoibaotaichinhvietnam.vn":   ThoiBaoTaiChinhContentCrawler,
    "thitruongtaichinhtiente.vn":  ThiTruongContentCrawler,
}

# Cache instances so we don't re-create them per URL
_instances = {}


def get_content_crawler(url: str):
    """
    Return the appropriate content crawler instance for the given URL.
    Returns None if the domain is not supported.
    """
    domain = urlparse(url).netloc.lower().lstrip("www.")
    # Try full domain, then base domain
    for key in DOMAIN_MAP:
        if key in domain:
            if key not in _instances:
                _instances[key] = DOMAIN_MAP[key]()
            return _instances[key]
    return None
