"""
ticker_tagger.py — Bước (1) GẮN MÃ: xác định mỗi tin nói về (các) mã VN30 nào.

Rule-based, không cần ML:
  - Ticker code  : match NGUYÊN TỪ VIẾT HOA  (vd "HPG", "(VCB)", "mã FPT")
                   → "gas" thường không khớp "GAS" vì khác hoa/thường.
  - Tên công ty  : match không phân biệt hoa thường, theo từ điển config.
  - Blacklist    : loại false positive cho vài ticker dễ nhầm với từ tiếng Anh.

API:
    tagger = TickerTagger.from_config()
    tagger.tag("Hòa Phát (HPG) báo lãi quý 2...")  -> ["HPG"]
    tagger.tag("Thị trường chung đỏ lửa")          -> []   (tin thị trường chung)
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "vn30_companies.yml"

# Cụm từ chứa ticker nhưng KHÔNG phải nói về mã đó (chống false positive)
TICKER_BLACKLIST = {
    "GAS": ["NATURAL GAS"],          # khí đốt nói chung
    "VIC": ["VICTORY", "VICTOR"],
    "SAB": [],
    "VRE": [],
    "BID": [],
}


class TickerTagger:
    def __init__(self, vn30: dict):
        self.vn30 = vn30
        self.tickers = sorted(vn30.keys())

        # Regex 1: ticker code nguyên từ (giữ nguyên hoa/thường để so khớp viết hoa)
        self.ticker_re = re.compile(
            r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, self.tickers)) + r")(?![A-Za-z0-9])"
        )

        # Regex 2: tên công ty (case-insensitive), longest-first để ưu tiên cụm dài
        name_to_ticker = {}
        for t, entry in vn30.items():
            for nm in entry.get("names", []) or []:
                nm = nm.strip()
                if nm:
                    name_to_ticker[nm] = t
        self.name_to_ticker = name_to_ticker
        names_sorted = sorted(name_to_ticker, key=len, reverse=True)
        self.name_re = (
            re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names_sorted) + r")(?!\w)",
                       re.IGNORECASE | re.UNICODE)
            if names_sorted else re.compile(r"(?!x)x")
        )

    # ── Loader ──
    @classmethod
    def from_config(cls, path: str | Path = CONFIG_PATH) -> "TickerTagger":
        with open(path, encoding="utf-8") as f:
            vn30 = yaml.safe_load(f)
        return cls(vn30)

    # ── Core ──
    def tag(self, text: str) -> list[str]:
        """Trả về list mã VN30 (không trùng) mà text nhắc tới."""
        if not text:
            return []
        found: set[str] = set()

        # 1) Ticker code viết hoa nguyên từ
        for m in self.ticker_re.finditer(text):
            tk = m.group(1)
            if tk != tk.upper():        # chỉ nhận khi đúng dạng viết hoa
                continue
            # kiểm tra blacklist quanh vị trí match
            lo, hi = max(0, m.start() - 20), min(len(text), m.end() + 20)
            window = text[lo:hi].upper()
            if any(bad in window for bad in TICKER_BLACKLIST.get(tk, [])):
                continue
            found.add(tk)

        # 2) Tên công ty
        for m in self.name_re.finditer(text):
            hit = m.group(1)
            tk = self.name_to_ticker.get(hit) or next(
                (t for k, t in self.name_to_ticker.items() if k.lower() == hit.lower()), None
            )
            if tk:
                found.add(tk)

        return sorted(found)

    def tag_article(self, title: str, content: str = "") -> list[str]:
        """Gắn mã dựa trên title + content."""
        return self.tag(f"{title or ''}\n{content or ''}")
