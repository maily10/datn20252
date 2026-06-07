"""
evaluate.py — Đánh giá MỘT phương pháp duy nhất (Hướng A, hybrid PhoBERT + lexicon)
trên gold set CafeF, sinh con số cho báo cáo.

Phương pháp:
  s(t) = (1−α)·[ P(pos|t) − P(neg|t) ]  +  α·tanh( k · net_lex(t) )       ∈ [−1, 1]

Tinh chỉnh hai bước (TRÁNH ĐOÁN MÒ):
  Bước 1 — Tinh chỉnh (α, k) trên TRAIN, tối ưu BINARY macro-F1
           (mục tiêu vận hành: đo trực tiếp chất lượng tín hiệu hướng).
  Bước 2 — Tinh chỉnh τ trên TRAIN, tối ưu 3-LỚP macro-F1 (giữ α, k cố định).
           τ là tham số *trình bày*, không phải của method.

Đánh giá trên TEST:
  • Polarity (pos vs neg) = sign(s) trên các tin gold ∈ {pos, neg}    ← chính
  • 3-class (neg/neu/pos) qua ngưỡng τ                                 ← cho minh bạch
Cùng baseline model-thuần để cô lập đóng góp của lexicon.

  python evaluate.py
"""
import json
import math
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

for _pkg in ("sklearn",):
    try:
        __import__(_pkg)
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "scikit-learn"])

from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

from lib.finance_lexicon import FinanceLexicon
from lib.sentiment_scorer import SentimentScorer

GOLD = ROOT / "data" / "gold_cafef.csv"
OUT_DIR = ROOT / "output"
L3 = ["negative", "neutral", "positive"]
L2 = ["negative", "positive"]

A_GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
K_GRID = [0.4, 0.6, 0.8, 1.0]
TAU_GRID = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def f1m(y, p, labels):
    return f1_score(y, p, labels=labels, average="macro", zero_division=0)


def acc(y, p):
    return sum(int(a == b) for a, b in zip(y, p)) / len(y)


def fused(ms, net, alpha, k):
    return (1 - alpha) * ms + alpha * math.tanh(k * net)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(GOLD).dropna(subset=["title", "label"]).reset_index(drop=True)
    tr_idx, te_idx = train_test_split(df.index, test_size=0.3, random_state=42,
                                      stratify=df["label"])
    tr_idx, te_idx = list(tr_idx), list(te_idx)
    titles = df["title"].astype(str).tolist()
    y_all = df["label"].tolist()

    print(f"Gold: {len(df)} | train={len(tr_idx)} test={len(te_idx)}")
    print(f"Phân bố: {df['label'].value_counts().to_dict()}")

    print("\nLoad PhoBERT + chấm 1005 tiêu đề (CPU, ~1-2 phút)...")
    sc = SentimentScorer()
    lex = FinanceLexicon.from_config()
    res = sc.score_batch(titles, batch_size=32)
    s_model = [r.score for r in res]
    s_argmax = [r.label for r in res]
    s_net = [lex.score(t).net for t in titles]

    def split(arr):
        return [arr[i] for i in tr_idx], [arr[i] for i in te_idx]
    tr_m, te_m = split(s_model)
    tr_a, te_a = split(s_argmax)
    tr_n, te_n = split(s_net)
    tr_y, te_y = split(y_all)

    def to_bin(ys, ms, ns):
        y2, m2, n2 = [], [], []
        for y, m, n in zip(ys, ms, ns):
            if y != "neutral":
                y2.append(y); m2.append(m); n2.append(n)
        return y2, m2, n2
    bt_y, bt_m, bt_n = to_bin(tr_y, tr_m, tr_n)
    be_y, be_m, be_n = to_bin(te_y, te_m, te_n)

    # ── Bước 1: (α, k) ← argmax binary F1 trên train ──
    print("\nBước 1: tune (α, k) trên TRAIN, tối ưu binary macro-F1...")
    best = (-1.0, None, None)
    for a in A_GRID:
        for k in K_GRID:
            p = ["positive" if fused(m, n, a, k) > 0 else "negative"
                 for m, n in zip(bt_m, bt_n)]
            f = f1m(bt_y, p, L2)
            if f > best[0]:
                best = (f, a, k)
    _, alpha, k = best
    print(f"  → α={alpha}, k={k}  (train binary F1 = {best[0]:.4f})")

    # ── Bước 2: τ ← argmax 3-class F1 trên train (giữ α, k) ──
    print("\nBước 2: tune τ trên TRAIN cho lens 3-lớp (giữ α, k)...")
    best_t = (-1.0, None)
    for t in TAU_GRID:
        p = []
        for m, n in zip(tr_m, tr_n):
            s = fused(m, n, alpha, k)
            p.append("positive" if s > t else "negative" if s < -t else "neutral")
        f = f1m(tr_y, p, L3)
        if f > best_t[0]:
            best_t = (f, t)
    _, tau = best_t
    print(f"  → τ={tau}  (train 3-class F1 = {best_t[0]:.4f})")

    # ── Đánh giá TEST ──
    print("\n" + "=" * 72 + "\nKẾT QUẢ TRÊN TEST\n" + "=" * 72)

    # 3-lớp argmax (baseline model thuần)
    a_arg = acc(te_y, te_a); f_arg = f1m(te_y, te_a, L3)
    print(f"\n[3 lớp] Baseline: PhoBERT argmax              acc={a_arg:.3f}  F1={f_arg:.3f}")

    # 3-lớp hybrid
    tp_hyb = []
    for m, n in zip(te_m, te_n):
        s = fused(m, n, alpha, k)
        tp_hyb.append("positive" if s > tau else "negative" if s < -tau else "neutral")
    at_hyb = acc(te_y, tp_hyb); ft_hyb = f1m(te_y, tp_hyb, L3)
    print(f"[3 lớp] ★ Hybrid (Hướng A)                    acc={at_hyb:.3f}  F1={ft_hyb:.3f}")
    print(classification_report(te_y, tp_hyb, labels=L3, digits=3, zero_division=0))
    cm = confusion_matrix(te_y, tp_hyb, labels=L3)
    print("Confusion 3-lớp [hàng=thật, cột=đoán: neg neu pos]:")
    for lab, row in zip(L3, cm):
        print(f"  {lab:<9} {row}")

    # Polarity (binary) baseline + hybrid
    bp_mod = ["positive" if m > 0 else "negative" for m in be_m]
    ab_mod = acc(be_y, bp_mod); fb_mod = f1m(be_y, bp_mod, L2)
    bp_hyb = ["positive" if fused(m, n, alpha, k) > 0 else "negative"
              for m, n in zip(be_m, be_n)]
    ab_hyb = acc(be_y, bp_hyb); fb_hyb = f1m(be_y, bp_hyb, L2)
    print(f"\n[Polarity n={len(be_y)}] Baseline: PhoBERT sign       acc={ab_mod:.3f}  F1={fb_mod:.3f}")
    print(f"[Polarity n={len(be_y)}] ★ Hybrid (Hướng A)           acc={ab_hyb:.3f}  F1={fb_hyb:.3f}")
    print(classification_report(be_y, bp_hyb, labels=L2, digits=3, zero_division=0))

    # ── Save ──
    cfg = {
        "method": "hybrid_continuous_score",
        "formula": "s(t) = (1-alpha)*[P(pos)-P(neg)] + alpha*tanh(k*net_lex)",
        "alpha": alpha, "k": k, "tau_for_3cls_view": tau,
        "model": "wonrax/phobert-base-vietnamese-sentiment",
        "lexicon": "config/finance_lexicon.yml",
        "gold_set": "data/gold_cafef.csv (CafeF 1005)",
        "split": {"train": len(tr_idx), "test": len(te_idx), "seed": 42, "stratified": True},
        "results_test": {
            "polarity": {"hybrid": {"acc": round(ab_hyb, 4), "macro_f1": round(fb_hyb, 4)},
                         "baseline_phobert": {"acc": round(ab_mod, 4), "macro_f1": round(fb_mod, 4)},
                         "n": len(be_y)},
            "three_class": {"hybrid": {"acc": round(at_hyb, 4), "macro_f1": round(ft_hyb, 4)},
                            "baseline_phobert_argmax": {"acc": round(a_arg, 4), "macro_f1": round(f_arg, 4)},
                            "n": len(te_y)},
        }
    }
    (OUT_DIR / "method_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                                encoding="utf-8")

    te_titles = [titles[i] for i in te_idx]
    te_scores = [fused(te_m[i], te_n[i], alpha, k) for i in range(len(te_idx))]
    pd.DataFrame({
        "title": te_titles, "true": te_y,
        "score": [round(s, 4) for s in te_scores],
        "polarity": ["positive" if s > 0 else "negative" for s in te_scores],
        "label_3cls": tp_hyb,
        "model_score": [round(te_m[i], 4) for i in range(len(te_idx))],
        "lex_net": te_n,
    }).to_csv(OUT_DIR / "eval_results.csv", index=False, encoding="utf-8")
    print(f"\nĐã ghi:\n  {OUT_DIR/'method_config.json'}\n  {OUT_DIR/'eval_results.csv'}")


if __name__ == "__main__":
    main()
