"""
evaluate_correlation.py — Mốc 4: đánh giá LIÊN HỆ sentiment ↔ điểm thay đổi giá VN30.

Theo plan PHAT_HIEN_DIEM_THAY_DOI.md §3 — 4 chỉ số BẮT BUỘC:
  1. Coverage     — % CP có ≥1 tin trong cửa sổ [−3, +1] ngày (cùng mã hoặc MARKET).
  2. Match rate   — % CP thoả sign(direction_CP) == sign(mean_score trong cửa sổ).
  3. Permutation test cho match rate (1.000 shuffles ngày tin).
  4. Bootstrap 95% CI cho match rate (1.000 resamples các CP có signal).
+ biểu đồ minh hoạ.

  python evaluate_correlation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
SENTI = ROOT.parent / "test" / "news_sentiment" / "output" / "news_sentiment_hybrid.csv"
MAPPING = ROOT.parent / "test" / "news_sentiment" / "output" / "news_stock_mapping.csv"
LINKS = ROOT.parent / "stocknewscrawl" / "vnstocknewsdata" / "news_links.csv"
PRICES = ROOT.parent / "vnstockprice" / "technical_indicators.csv"
CP_FILE = ROOT / "output" / "change_points.csv"
OUT_DIR = ROOT / "output"
PLOTS_DIR = OUT_DIR / "plots"

WIN_BEFORE = 3
WIN_AFTER = 1
N_PERM = 1000
N_BOOT = 1000
SEED = 42

REPR_SYMBOLS = ["VCB", "HPG", "VIC"]   # biểu đồ price + sentiment + CP


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_data():
    print("Đọc dữ liệu...")
    sent = pd.read_csv(SENTI, dtype={"news_id": str})
    sent = sent.drop_duplicates("news_id").reset_index(drop=True)
    print(f"  sentiment: {len(sent):,} bài (đã dedup)")

    mp = pd.read_csv(MAPPING, dtype={"news_id": str, "symbol": str})
    print(f"  mapping  : {len(mp):,} dòng (many-to-many), {mp.symbol.nunique()} symbol")

    links = pd.read_csv(LINKS, dtype=str, usecols=["id", "published_at"])
    links = links.rename(columns={"id": "news_id"})
    links["date"] = pd.to_datetime(links["published_at"]).dt.date.astype(str)
    links = links[["news_id", "date"]].drop_duplicates("news_id")
    print(f"  links    : {len(links):,} bài có ngày")

    cp = pd.read_csv(CP_FILE, dtype={"symbol": str})
    cp["change_point_date"] = pd.to_datetime(cp["change_point_date"]).dt.date.astype(str)
    print(f"  CP       : {len(cp)} điểm")

    # Join: mỗi dòng = (news_id, symbol_or_MARKET, date, score)
    df = (mp.merge(sent[["news_id", "score"]], on="news_id", how="inner")
            .merge(links, on="news_id", how="inner"))
    df = df.dropna(subset=["date", "score", "symbol"]).reset_index(drop=True)
    df["score"] = df["score"].astype(float)
    # Lọc ngày hợp lệ (drop NaT sau to_datetime)
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date_dt"]).reset_index(drop=True)
    df["date"] = df["date_dt"].dt.date.astype(str)
    df = df.drop(columns="date_dt")
    print(f"  → joined : {len(df):,} dòng (news × symbol-or-MARKET, đã lọc NaN)")
    return df, cp, links


def build_daily_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    """daily_sentiment(symbol, date) = mean(score), n_news."""
    g = df.groupby(["symbol", "date"])["score"].agg(["mean", "count"]).reset_index()
    g.columns = ["symbol", "date", "mean_score", "n_news"]
    return g


def encode_for_speed(df: pd.DataFrame, cp: pd.DataFrame):
    """Encode dates → int (days since epoch) & symbols → int code, sort theo date."""
    epoch = pd.Timestamp("2020-01-01")
    df = df.copy()
    df["date_int"] = (pd.to_datetime(df["date"]) - epoch).dt.days.astype(int)
    cp = cp.copy()
    cp["cp_int"] = (pd.to_datetime(cp["change_point_date"]) - epoch).dt.days.astype(int)

    syms = sorted(set(df.symbol.unique()) | set(cp.symbol.unique()) | {"MARKET"})
    sym2code = {s: i for i, s in enumerate(syms)}
    MARKET_CODE = sym2code["MARKET"]

    df["sym_code"] = df["symbol"].map(sym2code).astype(int)
    cp["sym_code"] = cp["symbol"].map(sym2code).astype(int)

    # Sort theo date_int để binary search
    df_sorted = df.sort_values("date_int").reset_index(drop=True)
    date_arr = df_sorted["date_int"].values
    sym_arr = df_sorted["sym_code"].values
    score_arr = df_sorted["score"].values
    news_id_arr = df_sorted["news_id"].values  # để shuffle theo news_id

    return df_sorted, date_arr, sym_arr, score_arr, news_id_arr, cp, MARKET_CODE


def match_per_cp(date_arr, sym_arr, score_arr, cp_int, cp_sym, cp_dir,
                 MARKET_CODE, before=3, after=1):
    """Returns 3 arrays length len(cp): covered (bool), has_signal (bool), match (bool)."""
    n = len(cp_int)
    covered = np.zeros(n, dtype=bool)
    has_signal = np.zeros(n, dtype=bool)
    match = np.zeros(n, dtype=bool)
    for i in range(n):
        cd = cp_int[i]
        lo = np.searchsorted(date_arr, cd - before, side="left")
        hi = np.searchsorted(date_arr, cd + after, side="right")
        if lo == hi:
            continue
        sub_sym = sym_arr[lo:hi]
        sub_score = score_arr[lo:hi]
        mask = (sub_sym == cp_sym[i]) | (sub_sym == MARKET_CODE)
        if not mask.any():
            continue
        covered[i] = True
        m = sub_score[mask].mean()
        if m == 0:
            continue
        has_signal[i] = True
        if (cp_dir[i] == 1 and m > 0) or (cp_dir[i] == -1 and m < 0):
            match[i] = True
    return covered, has_signal, match


def permutation_test(news_id_arr, date_arr, sym_arr, score_arr,
                     cp_int, cp_sym, cp_dir, MARKET_CODE, observed_rate, n_perm=1000):
    """Tráo ngày của các tin theo news_id (unique), 1000 lần. Trả về null dist + p-value."""
    # Lấy unique (news_id → date) để tráo cấp news_id, không cấp dòng
    unique_nid, first_idx = np.unique(news_id_arr, return_index=True)
    unique_date = date_arr[first_idx]

    nid_to_score = dict(zip(news_id_arr, score_arr))  # các dòng cùng news_id → cùng score
    nid_to_sym = sym_arr   # nguyên array (mapping dòng), KHÔNG đổi khi shuffle date

    rng = np.random.default_rng(SEED)
    null_rates = np.zeros(n_perm)

    for p in range(n_perm):
        # Tráo dates trong unique_date pool, gán lại cho từng news_id
        shuffled = rng.permutation(unique_date)
        nid_to_new_date = dict(zip(unique_nid, shuffled))
        # Áp vào toàn bộ dòng theo news_id
        new_date_arr = np.array([nid_to_new_date[nid] for nid in news_id_arr])

        # Re-sort
        order = np.argsort(new_date_arr)
        da = new_date_arr[order]
        sa = sym_arr[order]
        sc = score_arr[order]

        _, has_sig, mt = match_per_cp(da, sa, sc, cp_int, cp_sym, cp_dir,
                                      MARKET_CODE, WIN_BEFORE, WIN_AFTER)
        n_sig = int(has_sig.sum())
        null_rates[p] = mt.sum() / n_sig if n_sig > 0 else 0.0

        if (p + 1) % 100 == 0:
            print(f"    perm {p+1}/{n_perm}")

    # p-value: P(null >= observed)  (one-sided, hệ thống nghi observed > null)
    pval_oneside = float((null_rates >= observed_rate).mean())
    # two-sided (đối xứng quanh trung bình null)
    null_mean = null_rates.mean()
    deviation = abs(observed_rate - null_mean)
    pval_twoside = float((np.abs(null_rates - null_mean) >= deviation).mean())

    return null_rates, pval_oneside, pval_twoside


def bootstrap_ci(match_array, n_boot=1000, ci=95):
    """Bootstrap CI cho match rate. match_array: 0/1 array chỉ các CP có signal."""
    rng = np.random.default_rng(SEED + 1)
    n = len(match_array)
    if n == 0:
        return (0.0, 0.0)
    rates = np.array([match_array[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    alpha = (100 - ci) / 2
    return float(np.percentile(rates, alpha)), float(np.percentile(rates, 100 - alpha))


def plot_permutation_null(null_rates, observed, pval, save_path):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(null_rates, bins=40, color="#888", alpha=0.7, edgecolor="white",
            label=f"Phân phối null (n={len(null_rates)} shuffle)")
    ax.axvline(observed, color="#d62728", linewidth=2.5,
               label=f"Match rate quan sát = {observed:.3f}")
    ax.axvline(null_rates.mean(), color="#2ca02c", linewidth=1.5, linestyle="--",
               label=f"Trung bình null = {null_rates.mean():.3f}")
    ax.set_xlabel("Match rate")
    ax.set_ylabel("Số lần shuffle")
    ax.set_title(f"Permutation test cho match rate  (p-value hai phía = {pval:.4f})")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.close()


def plot_match_rate_by_symbol(per_sym_df, save_path):
    df = per_sym_df.sort_values("match_rate")
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = ["#d62728" if r < 0.5 else "#2ca02c" for r in df["match_rate"]]
    ax.barh(df["symbol"], df["match_rate"], color=colors, alpha=0.85)
    ax.axvline(0.5, color="black", linestyle="--", alpha=0.5, label="50% (ngẫu nhiên)")
    ax.set_xlabel("Match rate")
    ax.set_title("Match rate quanh điểm thay đổi — theo mã VN30")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.close()


def plot_price_sentiment_cp(symbol, prices, daily_sent, cps, save_path):
    fig, ax1 = plt.subplots(figsize=(13, 5))
    p = prices[prices["symbol"] == symbol].dropna(subset=["close"]).copy()
    p["date_dt"] = pd.to_datetime(p["date"])
    ax1.plot(p["date_dt"], p["close"], color="#1f77b4", linewidth=1.0, label="Close")
    ax1.set_ylabel("Close (nghìn VND)", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.grid(alpha=0.3)

    # Sentiment overlay — rolling mean để mượt
    s = daily_sent[daily_sent["symbol"].isin([symbol, "MARKET"])].copy()
    s["date_dt"] = pd.to_datetime(s["date"])
    s = s.sort_values("date_dt").groupby("date_dt", as_index=False)["mean_score"].mean()
    s["sent_smooth"] = s["mean_score"].rolling(window=20, min_periods=5).mean()
    ax2 = ax1.twinx()
    ax2.plot(s["date_dt"], s["sent_smooth"], color="#ff7f0e", linewidth=1.0, alpha=0.8,
             label="Daily sentiment (MA20)")
    ax2.axhline(0, color="#ff7f0e", linestyle=":", alpha=0.4)
    ax2.set_ylabel("Sentiment (MA20)", color="#ff7f0e")
    ax2.tick_params(axis="y", labelcolor="#ff7f0e")

    # CP markers
    n_up = n_down = 0
    for _, row in cps[cps["symbol"] == symbol].iterrows():
        color = "#2ca02c" if row["direction"] == 1 else "#d62728"
        ax1.axvline(pd.to_datetime(row["change_point_date"]),
                    color=color, alpha=0.45, linewidth=1.0)
        if row["direction"] == 1:
            n_up += 1
        else:
            n_down += 1

    ax1.set_title(f"{symbol} — giá + sentiment MA20 + CP (xanh +{n_up} / đỏ −{n_down})")
    ax1.set_xlabel("Ngày")
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.close()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    np.random.seed(SEED)

    print("\n[1/6] Load & join dữ liệu")
    df, cp, _ = load_data()

    print("\n[2/6] Tính daily_sentiment")
    daily = build_daily_sentiment(df)
    daily.to_csv(OUT_DIR / "daily_sentiment.csv", index=False, encoding="utf-8")
    print(f"  daily_sentiment.csv: {len(daily):,} dòng (mã × ngày)")

    print("\n[3/6] Encode cho tốc độ + tính match per CP (observed)")
    df_s, date_arr, sym_arr, score_arr, news_id_arr, cp_s, MARKET_CODE = encode_for_speed(df, cp)
    cp_int = cp_s["cp_int"].values
    cp_sym = cp_s["sym_code"].values
    cp_dir = cp_s["direction"].values

    covered, has_signal, match = match_per_cp(
        date_arr, sym_arr, score_arr, cp_int, cp_sym, cp_dir,
        MARKET_CODE, WIN_BEFORE, WIN_AFTER)

    n_total = len(cp_s)
    n_cov = int(covered.sum())
    n_sig = int(has_signal.sum())
    n_match = int(match[has_signal].sum())
    coverage = n_cov / n_total
    match_rate = n_match / n_sig if n_sig > 0 else 0.0

    print(f"  Tổng CP             : {n_total}")
    print(f"  Có tin (coverage)   : {n_cov} ({coverage:.3f})")
    print(f"  Có signal (≠ 0)     : {n_sig}")
    print(f"  Match               : {n_match}/{n_sig} = {match_rate:.4f}")

    print(f"\n[4/6] Permutation test (n={N_PERM} shuffles)")
    null_rates, pval_one, pval_two = permutation_test(
        news_id_arr, date_arr, sym_arr, score_arr,
        cp_int, cp_sym, cp_dir, MARKET_CODE, match_rate, N_PERM)
    print(f"  Null mean           : {null_rates.mean():.4f}  (std {null_rates.std():.4f})")
    print(f"  p-value (1 phía)    : {pval_one:.4f}")
    print(f"  p-value (2 phía)    : {pval_two:.4f}")
    print(f"  → {'BÁC' if pval_two < 0.05 else 'KHÔNG bác'} H₀ ở α=0.05")

    print(f"\n[5/6] Bootstrap 95% CI (n={N_BOOT} resamples)")
    match_signal = match[has_signal].astype(int)
    ci_lo, ci_hi = bootstrap_ci(match_signal, N_BOOT, 95)
    print(f"  Match rate = {match_rate:.4f}  [95% CI: {ci_lo:.4f}, {ci_hi:.4f}]")

    # Per-symbol breakdown
    print("\n[Per-symbol]")
    per_sym = []
    for sym in sorted(set(cp_s["symbol"].unique())):
        idx = cp_s["symbol"] == sym
        n_t = int(idx.sum())
        n_c = int(covered[idx].sum())
        sig_idx = has_signal & idx.values
        n_s = int(sig_idx.sum())
        n_m = int(match[sig_idx].sum())
        per_sym.append({
            "symbol": sym,
            "n_cp": n_t,
            "n_covered": n_c,
            "coverage": round(n_c / n_t, 3) if n_t else 0.0,
            "n_with_signal": n_s,
            "n_match": n_m,
            "match_rate": round(n_m / n_s, 3) if n_s else None,
        })
    per_sym_df = pd.DataFrame(per_sym)
    per_sym_df.to_csv(OUT_DIR / "correlation_summary.csv", index=False, encoding="utf-8")
    print(per_sym_df.to_string(index=False))

    # Save tests
    tests = {
        "scope": {
            "n_change_points": n_total,
            "window_before_days": WIN_BEFORE,
            "window_after_days": WIN_AFTER,
            "n_permutations": N_PERM,
            "n_bootstrap": N_BOOT,
            "seed": SEED,
        },
        "observed": {
            "coverage": round(coverage, 4),
            "match_rate": round(match_rate, 4),
            "n_covered": n_cov,
            "n_with_signal": n_sig,
            "n_match": n_match,
        },
        "permutation_test": {
            "null_mean": round(float(null_rates.mean()), 4),
            "null_std": round(float(null_rates.std()), 4),
            "p_value_one_sided": round(pval_one, 4),
            "p_value_two_sided": round(pval_two, 4),
            "reject_H0_alpha_005": bool(pval_two < 0.05),
        },
        "bootstrap_ci_95": {"lower": round(ci_lo, 4), "upper": round(ci_hi, 4)},
    }
    (OUT_DIR / "correlation_tests.json").write_text(
        json.dumps(tests, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  correlation_summary.csv + correlation_tests.json đã ghi")

    # Save null distribution
    np.save(OUT_DIR / "null_rates.npy", null_rates)

    # ── 6. Plots ──
    print("\n[6/6] Vẽ biểu đồ")
    plot_permutation_null(null_rates, match_rate, pval_two,
                          PLOTS_DIR / "permutation_null_histogram.png")
    print(f"  → permutation_null_histogram.png")

    plot_match_rate_by_symbol(per_sym_df.dropna(subset=["match_rate"]),
                              PLOTS_DIR / "match_rate_by_symbol.png")
    print(f"  → match_rate_by_symbol.png")

    prices = pd.read_csv(PRICES, dtype={"symbol": str})
    for sym in REPR_SYMBOLS:
        plot_price_sentiment_cp(sym, prices, daily, cp,
                                PLOTS_DIR / f"price_sentiment_cp_{sym}.png")
        print(f"  → price_sentiment_cp_{sym}.png")

    print(f"\n✅ Xong. Output trong {OUT_DIR}/")


if __name__ == "__main__":
    main()
