from .vneconomy import VnEconomyCrawler
from .baodautu import BaoDauTuCrawler
from .thoibaotaichinh import ThoiBaoTaiChinhCrawler
from .thitruongtaichinh import ThiTruongTaiChinhCrawler

CRAWLERS = {
    "vneconomy":        VnEconomyCrawler,
    "baodautu":         BaoDauTuCrawler,
    "thoibaotaichinh":  ThoiBaoTaiChinhCrawler,
    "thitruongtaichinh": ThiTruongTaiChinhCrawler,
}


def get_crawler(webname: str, **kwargs):
    if webname not in CRAWLERS:
        raise ValueError(f"Unknown webname '{webname}'. Available: {list(CRAWLERS.keys())}")
    return CRAWLERS[webname](**kwargs)
