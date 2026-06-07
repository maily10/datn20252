"""
finance_lexicon.py — Lớp HIỆU CHỈNH tài chính cho Hướng A (hybrid).

Đếm số cụm từ tài chính tích cực / tiêu cực trong văn bản, có xử lý phủ định
(negation đảo cực cụm đứng ngay sau). Không dùng ML — minh bạch, giải thích được.

API:
    lex = FinanceLexicon.from_config()
    hit = lex.score("TCB chia cổ tức tiền mặt 15%")
    # LexiconHit(pos_hits=2, neg_hits=0, matched_pos=['chia cổ tức','cổ tức tiền mặt'], ...)
    hit.net      # = pos_hits - neg_hits
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "finance_lexicon.yml"

# Cửa sổ ký tự trước một cụm để dò từ phủ định (≈ vài từ).
NEGATION_WINDOW = 18


@dataclass
class LexiconHit:
    pos_hits: int = 0
    neg_hits: int = 0
    matched_pos: list[str] = field(default_factory=list)
    matched_neg: list[str] = field(default_factory=list)

    @property
    def net(self) -> int:
        """Cực tính ròng = (số cụm tích cực) − (số cụm tiêu cực)."""
        return self.pos_hits - self.neg_hits


def _build_regex(phrases: list[str]) -> re.Pattern:
    """Gộp các cụm thành 1 regex, ưu tiên cụm DÀI trước (longest-first)."""
    if not phrases:
        return re.compile(r"(?!x)x")  # không bao giờ khớp
    ordered = sorted(set(phrases), key=len, reverse=True)
    body = "|".join(re.escape(p) for p in ordered)
    return re.compile(r"(?<!\w)(" + body + r")(?!\w)", re.IGNORECASE | re.UNICODE)


class FinanceLexicon:
    def __init__(self, positive: list[str], negative: list[str], negation: list[str]):
        self.pos_re = _build_regex(positive)
        self.neg_re = _build_regex(negative)
        # Phủ định: khớp ở cuối cửa sổ (ngay trước cụm)
        neg_body = "|".join(re.escape(n) for n in sorted(set(negation), key=len, reverse=True))
        self.negation_re = (
            re.compile(r"(?<!\w)(" + neg_body + r")(?!\w)", re.IGNORECASE | re.UNICODE)
            if negation else re.compile(r"(?!x)x")
        )

    @classmethod
    def from_config(cls, path: str | Path = CONFIG_PATH) -> "FinanceLexicon":
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cls(
            positive=cfg.get("positive", []) or [],
            negative=cfg.get("negative", []) or [],
            negation=cfg.get("negation", []) or [],
        )

    def _is_negated(self, text: str, start: int) -> bool:
        """Có từ phủ định trong cửa sổ ngay trước vị trí start không?"""
        lo = max(0, start - NEGATION_WINDOW)
        return self.negation_re.search(text, lo, start) is not None

    def score(self, text: str) -> LexiconHit:
        """Đếm cụm tích cực/tiêu cực; phủ định đảo cực cụm bị phủ định."""
        hit = LexiconHit()
        if not text:
            return hit

        # Cụm tích cực → nếu bị phủ định thì tính sang tiêu cực
        for m in self.pos_re.finditer(text):
            phrase = m.group(1).lower()
            if self._is_negated(text, m.start()):
                hit.neg_hits += 1
                hit.matched_neg.append(f"¬{phrase}")
            else:
                hit.pos_hits += 1
                hit.matched_pos.append(phrase)

        # Cụm tiêu cực → nếu bị phủ định thì tính sang tích cực
        for m in self.neg_re.finditer(text):
            phrase = m.group(1).lower()
            if self._is_negated(text, m.start()):
                hit.pos_hits += 1
                hit.matched_pos.append(f"¬{phrase}")
            else:
                hit.neg_hits += 1
                hit.matched_neg.append(phrase)

        return hit
