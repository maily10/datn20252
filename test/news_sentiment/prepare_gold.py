"""
prepare_gold.py — Chuẩn hoá gold set CafeF (raw_data.xlsx) để đánh giá sentiment.

Nguồn: repo 209sontung/Vietnamese-stock-article-classification (Dataset/raw_data.xlsx),
1.000 tiêu đề tin chứng khoán CafeF.vn gán nhãn (có hỗ trợ chuyên gia).
Nhãn gốc là số 1/2/3 → ánh xạ sang negative/neutral/positive.

  python prepare_gold.py
Đầu ra: data/gold_cafef.csv (title, label_int, label)
"""
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SRC = DATA / "raw_data.xlsx"
OUT = DATA / "gold_cafef.csv"

# Nhãn số → nhãn chuẩn (suy từ phân bố 1:187 neg / 2:248 neu / 3:565 pos)
INT2LABEL = {1: "negative", 2: "neutral", 3: "positive"}


def main():
    d = pd.read_excel(SRC)
    d = d.rename(columns={c: c.strip() for c in d.columns})
    d = d[["title", "label"]].dropna()
    d["label"] = d["label"].astype(int)

    print("Phân bố nhãn gốc (số):")
    print(d["label"].value_counts().sort_index().to_string())

    d["label_int"] = d["label"]
    d["label"] = d["label_int"].map(INT2LABEL)
    d = d.dropna(subset=["label"])

    print("\nPhân bố sau ánh xạ:")
    print(d["label"].value_counts().to_string())
    print("\nVí dụ mỗi nhãn:")
    for lab in ["negative", "neutral", "positive"]:
        print(f"\n--- {lab} ---")
        for t in d[d["label"] == lab]["title"].head(3):
            print("  ", str(t)[:78])

    d[["title", "label_int", "label"]].to_csv(OUT, index=False, encoding="utf-8")
    print(f"\nĐã ghi {len(d)} dòng → {OUT}")


if __name__ == "__main__":
    main()
