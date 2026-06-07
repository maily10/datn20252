"""
sentiment_scorer.py — Bước (2) SENTIMENT: chấm sắc thái pos/neg/neutral cho tin.

Dùng mô hình sentiment tiếng Việt pre-trained (HuggingFace), document-level.
Mặc định: wonrax/phobert-base-vietnamese-sentiment (3 lớp NEG/POS/NEU).

Tự ánh xạ id2label của model → {negative, neutral, positive} theo từ khoá,
nên đổi model khác (visobert...) vẫn chạy mà không cần sửa code.

API:
    scorer = SentimentScorer()                       # load model (lần đầu tải ~500MB)
    scorer.score_batch(["VCB báo lãi kỷ lục", ...])
    # -> [{"label": "positive", "score": 0.82, "probs": {...}}, ...]
"""
from __future__ import annotations

from dataclasses import dataclass

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

DEFAULT_MODEL = "wonrax/phobert-base-vietnamese-sentiment"
LABELS = ["negative", "neutral", "positive"]


@dataclass
class SentimentResult:
    label: str            # negative | neutral | positive
    score: float          # P(pos) - P(neg) ∈ [-1, 1]
    probs: dict           # {negative, neutral, positive}


def _map_label(raw: str) -> str | None:
    """Ánh xạ tên nhãn của model → negative/neutral/positive theo từ khoá."""
    s = raw.lower()
    if any(k in s for k in ["neg", "tiêu", "tieu", "xấu", "xau"]):
        return "negative"
    if any(k in s for k in ["pos", "tích", "tich", "tốt", "tot"]):
        return "positive"
    if any(k in s for k in ["neu", "trung"]):
        return "neutral"
    return None


class SentimentScorer:
    def __init__(self, model_name: str = DEFAULT_MODEL,
                 device: str | None = None, max_length: int = 256):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.max_length = max_length
        print(f"[sentiment] Loading {model_name} on {self.device}…")
        # Tokenizer: thử fast trước (visobert/XLM-R), fallback slow (PhoBERT BPE)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        except Exception:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval().to(self.device)

        # Ánh xạ index → negative/neutral/positive
        id2label = self.model.config.id2label
        self.idx_of = {}                      # {"negative": i, ...}
        for i, raw in id2label.items():
            mapped = _map_label(str(raw))
            if mapped:
                self.idx_of[mapped] = int(i)
        missing = set(LABELS) - set(self.idx_of)
        if missing:
            raise ValueError(f"Không map được nhãn {missing} từ id2label={id2label}")

    @torch.inference_mode()
    def score_batch(self, texts: list[str], batch_size: int = 16) -> list[SentimentResult]:
        results: list[SentimentResult] = []
        for start in range(0, len(texts), batch_size):
            chunk = [t if isinstance(t, str) and t.strip() else "." for t in texts[start:start + batch_size]]
            enc = self.tokenizer(chunk, padding=True, truncation=True,
                                 max_length=self.max_length, return_tensors="pt").to(self.device)
            probs = torch.softmax(self.model(**enc).logits, dim=-1)  # [B, n_label]
            for row in probs:
                p = {lab: float(row[self.idx_of[lab]]) for lab in LABELS}
                label = max(p, key=p.get)
                results.append(SentimentResult(
                    label=label,
                    score=round(p["positive"] - p["negative"], 4),
                    probs={k: round(v, 4) for k, v in p.items()},
                ))
        return results
