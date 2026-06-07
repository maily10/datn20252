"""
detect_change_points.py — Phát hiện điểm thay đổi giá cho VN30 (Mốc 3).

Theo plan trong PHAT_HIEN_DIEM_THAY_DOI.md:
  - Đầu vào: log_return từng mã (đã có trong technical_indicators.csv).
  - Thuật toán: PELT (ruptures, model="l2") trên log-return chuẩn hoá (zero-mean, unit-std).
  - Penalty: pen = c · log(n) với c = 3.0 (BIC-style, điều chỉnh nếu CP quá ít/nhiều).
  - Mỗi CP gán direction = sign(mean(after) − mean(before)) và magnitude = |chênh lệch|
    với cửa sổ 20 ngày trước/sau.
  - Đầu ra: change_points.csv + plots/cp_<mã>.png cho 4-6 mã đại diện.

  python detect_change_points.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import ruptures as rpt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "vnstockprice" / "technical_indicators.csv"
OUT_DIR = ROOT / "output"
PLOTS_DIR = OUT_DIR / "plots"

WINDOW = 20      # cửa sổ trước/sau CP để gán direction/magnitude
PEN_C = 0.5      # penalty constant trong pen = c * log(n)
MIN_DAYS = 100   # bỏ mã ít dữ liệu

# Mã đại diện để vẽ minh hoạ
REPR_SYMBOLS = ["VCB", "HPG", "FPT", "VIC", "MWG", "VNM"]


def detect_for_series(log_returns: np.ndarray) -> list[int]:
    """PELT trên log-return chuẩn hoá → list các index breakpoint (không gồm endpoint)."""
    mu, sigma = log_returns.mean(), log_returns.std()
    if sigma == 0:
        return []
    r_std = (log_returns - mu) / sigma
    n = len(r_std)
    pen = PEN_C * math.log(n)
    algo = rpt.Pelt(model="l2").fit(r_std.reshape(-1, 1))
    bkps = algo.predict(pen=pen)
    return bkps[:-1]  # endpoint cuối là n, bỏ


def direction_magnitude(log_returns: np.ndarray, idx: int) -> tuple[int, float]:
    """Hướng (+1/−1) và độ lớn |mean(after) − mean(before)| quanh CP idx."""
    n = len(log_returns)
    lo = max(0, idx - WINDOW)
    hi = min(n, idx + WINDOW)
    before = log_returns[lo:idx].mean() if idx > lo else 0.0
    after = log_returns[idx:hi].mean() if hi > idx else 0.0
    diff = float(after - before)
    return (1 if diff > 0 else -1), abs(diff)


def plot_symbol(price_df: pd.DataFrame, cps_df: pd.DataFrame, save_path: Path) -> None:
    """Biểu đồ giá close + vạch CP (xanh = tăng, đỏ = giảm)."""
    fig, ax = plt.subplots(figsize=(13, 4.5))
    dates = pd.to_datetime(price_df["date"])
    ax.plot(dates, price_df["close"], color="#1f77b4", linewidth=1.0, label="Close")
    n_up = n_down = 0
    for _, row in cps_df.iterrows():
        color = "#2ca02c" if row["direction"] == 1 else "#d62728"
        ax.axvline(pd.to_datetime(row["change_point_date"]),
                   color=color, alpha=0.55, linewidth=1.0)
        if row["direction"] == 1:
            n_up += 1
        else:
            n_down += 1
    sym = price_df["symbol"].iloc[0]
    ax.set_title(f"{sym} — giá Close + điểm thay đổi (xanh tăng: {n_up}, đỏ giảm: {n_down})")
    ax.set_xlabel("Ngày")
    ax.set_ylabel("Close (nghìn VND)")
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    plt.savefig(save_path, dpi=120)
    plt.close()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Đọc {SRC} ...")
    df = pd.read_csv(SRC, dtype={"symbol": str})
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
    print(f"  {len(df):,} dòng, {df['symbol'].nunique()} mã, "
          f"{df['date'].min()} → {df['date'].max()}")

    all_cps: list[dict] = []
    skipped: list[str] = []

    for symbol, group in df.groupby("symbol", sort=False):
        g = group.dropna(subset=["log_return"]).reset_index(drop=True)
        if len(g) < MIN_DAYS:
            skipped.append(symbol)
            continue
        log_returns = g["log_return"].astype(float).values
        dates = g["date"].values
        bkps = detect_for_series(log_returns)
        for bkp in bkps:
            if bkp <= 0 or bkp >= len(dates):
                continue
            d, m = direction_magnitude(log_returns, bkp)
            all_cps.append({
                "symbol": symbol,
                "change_point_date": str(dates[bkp]),
                "direction": d,
                "magnitude": round(m, 6),
            })

    if skipped:
        print(f"  ⚠️ Bỏ {len(skipped)} mã ít dữ liệu (<{MIN_DAYS} ngày): {skipped}")

    cp_df = pd.DataFrame(all_cps).sort_values(
        ["symbol", "change_point_date"]).reset_index(drop=True)

    out_csv = OUT_DIR / "change_points.csv"
    cp_df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n→ Ghi {out_csv}  ({len(cp_df)} CP)")

    # Thống kê
    n_syms = cp_df["symbol"].nunique()
    counts = cp_df.groupby("symbol").size()
    print(f"\n=== Thống kê CPD (penalty c = {PEN_C}) ===")
    print(f"  Số mã có CP: {n_syms}")
    print(f"  Tổng CP    : {len(cp_df)}")
    print(f"  CP/mã      : trung bình {counts.mean():.1f} | min {counts.min()} | "
          f"median {int(counts.median())} | max {counts.max()}")
    print(f"  Phân bố hướng: {cp_df['direction'].value_counts().to_dict()}")
    print(f"  Magnitude  : mean {cp_df['magnitude'].mean():.4f} | "
          f"median {cp_df['magnitude'].median():.4f} | max {cp_df['magnitude'].max():.4f}")

    # Top 5 CP có magnitude lớn nhất
    print(f"\n  Top 5 CP có magnitude lớn nhất:")
    top = cp_df.nlargest(5, "magnitude")[["symbol", "change_point_date", "direction", "magnitude"]]
    print(top.to_string(index=False))

    # Vẽ biểu đồ
    print(f"\nVẽ {len(REPR_SYMBOLS)} biểu đồ minh hoạ → {PLOTS_DIR}/")
    for sym in REPR_SYMBOLS:
        sub_price = df[df["symbol"] == sym].dropna(subset=["close"])
        sub_cps = cp_df[cp_df["symbol"] == sym]
        if not sub_price.empty:
            plot_symbol(sub_price, sub_cps, PLOTS_DIR / f"cp_{sym}.png")
            print(f"  → cp_{sym}.png  ({len(sub_cps)} CP)")

    # Vẽ overview: histogram CP count theo mã
    fig, ax = plt.subplots(figsize=(10, 4))
    counts.sort_values().plot(kind="bar", ax=ax, color="#1f77b4", alpha=0.85)
    ax.set_title(f"Số điểm thay đổi mỗi mã VN30 (penalty c = {PEN_C})")
    ax.set_ylabel("Số CP")
    ax.set_xlabel("Mã")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "cp_count_per_symbol.png", dpi=120)
    plt.close()
    print(f"  → cp_count_per_symbol.png")

    print(f"\n✅ Xong. Output trong {OUT_DIR}/")


if __name__ == "__main__":
    main()
