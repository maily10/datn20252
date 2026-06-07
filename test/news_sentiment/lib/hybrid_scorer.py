"""
hybrid_scorer.py — Hướng A: phương pháp hybrid PhoBERT + từ điển tài chính.

MỘT phương pháp duy nhất sinh điểm cực tính liên tục s(t) ∈ [−1, 1]:

    s_lex   = tanh(k · (pos_hits − neg_hits))                 ∈ [−1, 1]
    s(t)    = (1 − α) · s_model + α · s_lex                   ∈ [−1, 1]
              └── PhoBERT ──┘   └─ Finance Lexicon ─┘

  s(t) LÀ output của method — dùng trực tiếp cho tổng hợp/tương quan (Mốc 4).

Hai "lens" để rời rạc hoá s(t) (chỉ để báo cáo/người đọc, không phải method khác):
  • polarity  = "positive" nếu s>0, ngược lại "negative"        — mục tiêu vận hành
  • label_3cls= positive nếu s>τ, negative nếu s<−τ, neutral còn lại — cho trình bày

α, k là tham số của method (tinh chỉnh theo binary macro-F1).
τ là tham số *trình bày* cho lens 3 lớp (tinh chỉnh post-hoc).
Xem evaluate.py để biết quy trình.

API:
    sc = HybridSentimentScorer(alpha=0.6, k=1.0, tau=0.05)
    sc.score_batch(["TCB chia cổ tức tiền mặt 15%", ...])  # -> [HybridResult, ...]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from lib.finance_lexicon import FinanceLexicon
from lib.sentiment_scorer import DEFAULT_MODEL, SentimentScorer


@dataclass
class HybridResult:
    score: float          # ★ s(t) ∈ [−1, 1] — OUTPUT CHÍNH của method
    polarity: str         # view nhị phân:  "positive" nếu s>0, "negative" còn lại
    label_3cls: str       # view 3 lớp:     positive / negative / neutral (qua ngưỡng τ)
    model_score: float    # P(pos) − P(neg) — thành phần model
    model_label: str      # nhãn argmax của model (để so sánh baseline)
    lex_net: int          # pos_hits − neg_hits — net cụm khớp trong từ điển
    lex_score: float      # tanh(k · net) — thành phần lexicon
    matched_pos: list     # cụm tích cực đã khớp (giải thích/debug)
    matched_neg: list
    probs: dict           # P(neg), P(neu), P(pos) của model


def label_from_score(score: float, tau: float) -> str:
    """Rời rạc hoá s thành 3 lớp qua ngưỡng τ (chỉ dùng cho lens trình bày)."""
    if score > tau:
        return "positive"
    if score < -tau:
        return "negative"
    return "neutral"


class HybridSentimentScorer:
    def __init__(self, model_name: str = DEFAULT_MODEL,
                 alpha: float = 0.6, k: float = 1.0, tau: float = 0.05,
                 lexicon: FinanceLexicon | None = None,
                 device: str | None = None, max_length: int = 256):
        self.model = SentimentScorer(model_name=model_name, device=device, max_length=max_length)
        self.lex = lexicon or FinanceLexicon.from_config()
        self.alpha, self.tau, self.k = alpha, tau, k

    def score_batch(self, texts: list[str], batch_size: int = 16) -> list[HybridResult]:
        model_res = self.model.score_batch(texts, batch_size=batch_size)
        out: list[HybridResult] = []
        for text, mr in zip(texts, model_res):
            hit = self.lex.score(text or "")
            lex_score = math.tanh(self.k * hit.net)
            s = (1 - self.alpha) * mr.score + self.alpha * lex_score
            out.append(HybridResult(
                score=round(s, 4),
                polarity="positive" if s > 0 else "negative",
                label_3cls=label_from_score(s, self.tau),
                model_score=mr.score,
                model_label=mr.label,
                lex_net=hit.net,
                lex_score=round(lex_score, 4),
                matched_pos=hit.matched_pos,
                matched_neg=hit.matched_neg,
                probs=mr.probs,
            ))
        return out
