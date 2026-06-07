# Kế hoạch — Pipeline phân loại + ABSA tin tức VN30

Tài liệu này mô tả CHI TIẾT mọi thứ sẽ làm sau khi bạn review xong. Không có code thật, chỉ là design + ví dụ + schema để bạn check.

---

## 0. Mục tiêu

Từ file CSV `vnstocknewsdata/news_content.csv` (đã có sau bước crawl) → sinh ra file `vnstocknewsdata/news_labels.csv` với mỗi row là **1 entity** (1 mã / 1 ngành / 1 chỉ báo vĩ mô) trong **1 bài báo**, kèm:

| Field | Loại | Mô tả |
|---|---|---|
| `news_id` | int | join về `news_links.csv` |
| `tier` | 1 / 2 / 3 | tầng vĩ mô / ngành / công ty |
| `ticker` | str / null | mã CK (chỉ T3) |
| `sector` | str / null | tên ngành (T2, T3) |
| `label` | str | `positive` / `negative` / `neutral` |
| `sentiment_score` | float | trong khoảng [-1.0, +1.0] (= P(pos) − P(neg)) |
| `confidence` | float | trong khoảng [0, 1] = max(softmax 3 nhãn) |
| `extract` | str | snippet 1-3 câu chứa entity |
| `aspect` | str / null | khía cạnh (vd "giá thép", "lợi nhuận") — extract pass-2, tạm để rỗng |
| `published_at` | iso datetime | join từ `news_links.csv` |
| `method` | str | `rule+nli` / `rule_only` (debug) |
| `rule_matched_terms` | str | các từ khóa match được (debug) |

**Nguyên tắc cốt lõi:**
1. **Rule-base trước, model sau** — Rule lo việc *Tier nào* + *Entity nào*; model lo việc *Sentiment*.
2. **Company-first** — match công ty trước, suy ngược ra ngành; nếu trượt mới match ngành; trượt nốt mới gán vĩ mô.
3. **Snippet-based** — không bao giờ feed full content vào mDeBERTa; chỉ feed 1-3 câu chứa entity.
4. **Một bài → nhiều row** — 1 bài nhắc 3 mã → 3 row T3.

---

## 1. Cấu trúc thư mục mới (đặt trong `test/`)

```
e:\20252\datn\crawler\
├── stocknewscrawl/                  ← đã có (crawler)
│   └── vnstocknewsdata/
│       ├── news_links.csv
│       ├── news_content.csv
│       └── news_labels.csv          ← OUTPUT mới
└── test/
    └── news_classifier/             ← MODULE MỚI (đã tạo skeleton)
        ├── config/
        │   ├── vn30_companies.yml       ← từ điển 30 mã (việc thủ công)
        │   ├── sectors.yml              ← keyword ngành (TF-IDF + bạn duyệt)
        │   ├── sectors_draft.yml        ← bản nháp tự sinh (output Bước 1.5)
        │   └── macro_keywords.yml       ← keyword vĩ mô
        ├── classifier/
        │   ├── __init__.py
        │   ├── tier_classifier.py       ← rule-based
        │   ├── snippet_extractor.py
        │   └── absa_mdeberta.py         ← zero-shot NLI
        ├── tools/
        │   └── build_sector_keywords.py ← TF-IDF tự sinh sectors_draft.yml (Bước 1.5)
        ├── tests/
        │   ├── test_tier_classifier.py
        │   └── test_data/
        │       ├── samples.csv          ← 20 bài tự gán nhãn (1 row = 1 entity kỳ vọng)
        │       └── gold_100.csv         ← gold set validation
        ├── classify_news.py             ← entrypoint
        ├── requirements.txt             ← transformers, torch, pyyaml, scikit-learn, pyvi
        └── README.md
```

Không đụng vào `stocknewscrawl/`. Output ghi vào `stocknewscrawl/vnstocknewsdata/news_labels.csv` để các nơi khác đọc cùng folder.

Path tương đối từ `test/news_classifier/` về dữ liệu: `../../stocknewscrawl/vnstocknewsdata/...`

---

## 2. Bước 1 — `config/vn30_companies.yml`

### 2.1. Danh sách VN30 (kiểm tra lại với HOSE trước khi commit)

Danh sách VN30 thay đổi mỗi quý, tôi liệt kê đợt gần nhất tôi biết — bạn cần **đối chiếu lại trên HOSE** trước khi dùng. Đợt 2025/Q2 (tham khảo):

```
ACB, BCM, BID, BVH, CTG, FPT, GAS, GVR, HDB, HPG,
LPB, MBB, MSN, MWG, PLX, SAB, SHB, SSB, SSI, STB,
TCB, TPB, VCB, VHM, VIB, VIC, VJC, VNM, VPB, VRE
```

### 2.2. Schema mỗi entry

```yaml
HPG:
  full_names:
    - "Tập đoàn Hòa Phát"
    - "Hòa Phát"
    - "Hoà Phát"        # cả "ò" và "oà"
    - "Hoa Phat"
  sector: "Thép"
  super_sector: "Nguyên vật liệu"
  exchange: "HOSE"
  ticker_aliases: []     # nếu có biến thể như "HPG-CW"
```

### 2.3. Mapping ngành dự kiến (toàn VN30)

| Sector | Tickers |
|---|---|
| Ngân hàng | ACB, BID, CTG, HDB, LPB, MBB, SHB, SSB, STB, TCB, TPB, VCB, VIB, VPB |
| Bất động sản | BCM, VHM, VIC, VRE |
| Bán lẻ | MWG |
| Thực phẩm & Đồ uống | MSN, SAB, VNM |
| Thép | HPG |
| Dầu khí | GAS, PLX |
| Công nghệ | FPT |
| Hàng không | VJC |
| Cao su | GVR |
| Bảo hiểm | BVH |
| Chứng khoán | SSI |

→ ~11 ngành. Tier 2 model classification chỉ chọn trong tập này (closed-set).

### 2.4. Lưu ý variant tên cần ghi đủ

Ví dụ Vingroup hay bị viết:
- "Vingroup", "Tập đoàn Vingroup", "VinGroup", "Vin Group", "VIC"

Sacombank:
- "Sacombank", "STB", "Sacom Bank", "Ngân hàng Sài Gòn Thương Tín"

→ Tôi sẽ chuẩn bị bản nháp đầy đủ, bạn duyệt + bổ sung.

---

## 2.5. Bước 1.5 — `tools/build_sector_keywords.py` (TF-IDF tự sinh keyword)

### 2.5.1. Tại sao có bước này

Plan gốc cần `sectors.yml` viết tay (Pass 2 trong `tier_classifier`). Cách viết tay có 2 vấn đề:
- Tốn công, dễ sót terminology thực tế trong báo Việt
- Bias chủ quan: "tôi nghĩ keyword X là về ngành Y" có thể sai

→ Thay bằng pipeline **TF-IDF auto-suggest** rồi user duyệt. Máy đề xuất, người chốt.

### 2.5.2. Bootstrap nhãn ngành (chicken-and-egg)

TF-IDF cần corpus đã có nhãn ngành. Ta KHÔNG có sẵn nhãn, nhưng có thể tự sinh nhãn weak từ **VN30 ticker → sector map** đã làm ở Bước 1:

```
Bài nào nhắc HPG ≥ 2 lần  → weak label "Thép"
Bài nào nhắc VCB ≥ 2 lần  → weak label "Ngân hàng"
Bài nào nhắc nhiều mã trong NHIỀU ngành  → loại (đa nhãn nhiễu)
Bài không nhắc mã nào VN30 → loại (không có label để học)
```

Với ~14000 bài đã crawl, ước tính có **~5000-7000 bài có nhãn ngành weak**, đủ để TF-IDF tin cậy.

### 2.5.3. Pipeline đầy đủ

```
INPUT : vnstocknewsdata/news_content.csv + config/vn30_companies.yml
OUTPUT: config/sectors_draft.yml   (bản nháp, user duyệt → đổi tên thành sectors.yml)

┌─────────────────────────────────────────────────┐
│ 1. Load news_content + vn30_companies           │
├─────────────────────────────────────────────────┤
│ 2. Weak labeling:                               │
│    for each article:                            │
│      - regex match VN30 ticker + tên CT         │
│      - nếu mã thuộc đúng 1 ngành (≥2 lần) → tag │
│      - nếu mã thuộc nhiều ngành → skip          │
├─────────────────────────────────────────────────┤
│ 3. Tokenize tiếng Việt (pyvi):                  │
│    "ngân hàng tăng trưởng tín dụng"             │
│  → "ngân_hàng tăng_trưởng tín_dụng"             │
├─────────────────────────────────────────────────┤
│ 4. TfidfVectorizer:                             │
│    - max_features = 20000                       │
│    - ngram_range = (1, 2)                       │
│    - min_df = 5  (xuất hiện ≥5 bài)             │
│    - max_df = 0.5  (loại từ quá phổ thông)      │
│    - stop_words = vietnamese stopwords list     │
├─────────────────────────────────────────────────┤
│ 5. Per-sector TF-IDF mean:                      │
│    docs_of_sector = bài có weak_label = sector  │
│    score(term, sector) =                        │
│      mean(tfidf của term trong docs_of_sector)  │
│      − mean(tfidf của term trong docs_other)    │
│    → term điểm CAO = đặc trưng cho sector       │
├─────────────────────────────────────────────────┤
│ 6. Pick top N terms per sector:                 │
│    - Top 50 unigram + bigram                    │
│    - Loại term chứa số (Q3, 2025…) → noise      │
│    - Loại term có trong tên VN30 company        │
│      (vì đó là tier-3, không phải sector)       │
├─────────────────────────────────────────────────┤
│ 7. Xuất sectors_draft.yml + báo cáo:            │
│    - Số bài weak-labeled mỗi sector             │
│    - Top 50 terms / sector kèm score            │
│    - 5 example article snippet / sector         │
│      (để bạn verify weak label đúng không)      │
└─────────────────────────────────────────────────┘
```

### 2.5.4. Code outline

```python
# tools/build_sector_keywords.py

import re, yaml
import pandas as pd
from collections import defaultdict
from pyvi import ViTokenizer
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# 1. Load
df = pd.read_csv("../stocknewscrawl/vnstocknewsdata/news_content.csv")
vn30 = yaml.safe_load(open("config/vn30_companies.yml"))
ticker_to_sector = {t: info["sector"] for t, info in vn30.items()}

# 2. Weak labeling
def assign_weak_sector(text):
    found_tickers = set(re.findall(r"(?<![A-Za-z0-9])(" + "|".join(vn30) + r")(?![A-Za-z0-9])", text))
    found_sectors = {ticker_to_sector[t] for t in found_tickers
                     if text.count(t) >= 2}
    if len(found_sectors) == 1:
        return next(iter(found_sectors))
    return None  # ambiguous hoặc no match → skip

df["weak_sector"] = df["content"].apply(assign_weak_sector)
labeled = df[df["weak_sector"].notna()].copy()
print(labeled["weak_sector"].value_counts())  # sanity check

# 3. Tokenize tiếng Việt
labeled["tokens"] = labeled["content"].apply(
    lambda t: ViTokenizer.tokenize(t).lower()
)

# 4. TF-IDF
STOP_VI = load_vietnamese_stopwords()  # ~700 từ, file kèm
vec = TfidfVectorizer(
    max_features=20000, ngram_range=(1, 2),
    min_df=5, max_df=0.5, stop_words=STOP_VI,
)
X = vec.fit_transform(labeled["tokens"])
vocab = vec.get_feature_names_out()

# 5. Per-sector mean TF-IDF, so với corpus khác
def top_terms_per_sector(X, labels, vocab, top_n=50):
    out = {}
    all_mean = np.asarray(X.mean(axis=0)).ravel()
    for sector in set(labels):
        mask = labels == sector
        sector_mean = np.asarray(X[mask].mean(axis=0)).ravel()
        diff = sector_mean - all_mean
        top_idx = diff.argsort()[::-1][:top_n*2]  # lấy dư để filter
        terms = [(vocab[i], float(diff[i])) for i in top_idx]
        # filter: bỏ ticker, bỏ tên company, bỏ token chứa số
        terms = [
            (t, s) for t, s in terms
            if not contains_ticker_or_name(t, vn30)
            and not re.search(r"\d", t)
        ][:top_n]
        out[sector] = terms
    return out

result = top_terms_per_sector(X, labeled["weak_sector"].values, vocab)

# 6. Xuất YAML draft
draft = {sector: [t for t, _ in terms] for sector, terms in result.items()}
yaml.dump(draft, open("config/sectors_draft.yml", "w"),
          allow_unicode=True, sort_keys=False)
```

### 2.5.5. Output `sectors_draft.yml` mẫu

```yaml
# AUTO-GENERATED bởi tools/build_sector_keywords.py
# Review thủ công, xoá noise, đổi tên thành sectors.yml trước khi dùng

"Ngân hàng":
  - "tín_dụng"
  - "lãi_suất_cho_vay"
  - "NHNN"
  - "NIM"
  - "huy_động"
  - "nợ_xấu"
  - "thanh_khoản"
  - "lợi_nhuận_trước_thuế"   # ← NOISE, áp dụng cho mọi ngành
  - "tăng_trưởng_tín_dụng"
  - ...

"Thép":
  - "HRC"
  - "thép_xây_dựng"
  - "quặng_sắt"
  - "giá_thép"
  - "lò_cao"
  - "thép_cuộn"
  - ...
```

### 2.5.6. Cảnh báo / pitfall

| Vấn đề | Biểu hiện | Khắc phục |
|---|---|---|
| **Token generic lọt top** | "khách_hàng", "doanh_thu", "lợi_nhuận" xuất hiện ở mọi ngành | TF-IDF dùng `max_df=0.5` lọc bớt; user vẫn cần xoá thủ công |
| **Bias từ weak label** | Bài về VCB cũng nhắc vĩ mô → "lạm_phát" lọt vào "Ngân hàng" | Yêu cầu ticker ≥ 2 lần + bài có ≥ 300 ký tự |
| **Sector ít data** | "Hàng không" chỉ có VJC → ít bài → TF-IDF không đủ tin cậy | Báo cáo số bài/sector; sector < 50 bài → đề xuất user tự bổ sung |
| **Tokenizer thất bại** | pyvi chia sai cụm tiếng Việt | Fallback: cũng tính TF-IDF không tokenize, dùng làm sanity check |
| **Mã ngoài VN30** | HSG (thép, không VN30) → bài nhắc HSG không được tag | OK, vì v1 chỉ học từ VN30; v2 có thể expand |
| **Ticker chứa trong từ Việt** | "GAS" cũng là viết tắt khí gas chung | Word-boundary regex như Bước 2 |

### 2.5.7. Quy trình bạn vận hành (sau khi tôi code xong)

```bash
cd test/news_classifier
python tools/build_sector_keywords.py \
  --content ../../stocknewscrawl/vnstocknewsdata/news_content.csv \
  --vn30    config/vn30_companies.yml \
  --output  config/sectors_draft.yml \
  --report  config/sectors_report.html    # có example snippet để verify
```

Sau đó:
1. Mở `sectors_report.html` xem 5 bài/sector — có đúng ngành không
2. Mở `sectors_draft.yml`, đọc lướt top 50 từ/sector, **xoá noise** (mất ~10 phút)
3. Đổi tên `sectors_draft.yml` → `sectors.yml`
4. Bước 2 (`tier_classifier.py`) sẽ load file này như fallback Pass 2

### 2.5.8. Câu hỏi mở: TF-IDF có thể dùng làm classifier không?

Có — tính cosine similarity giữa bài mới vs vector centroid của mỗi sector. Nhưng tôi KHÔNG đề xuất thay mDeBERTa:
- TF-IDF không hiểu context → không phân biệt "HSBC mở chi nhánh tại VN" (tin về CT cụ thể) vs "ngành ngân hàng đang khó khăn" (tin chung)
- Zero-shot NLI có thể đọc câu phủ định, ẩn dụ — TF-IDF không.

→ TF-IDF chỉ làm **build keyword dictionary**, classification thực tế vẫn mDeBERTa.

---

## 3. Bước 2 — `classifier/tier_classifier.py`

### 3.1. Input / Output

**Input**: 1 article = `{news_id, title, summary, content, published_at}`
**Output**: list các dict, mỗi dict 1 entity:
```python
[
  {"tier": 3, "ticker": "HPG", "sector": "Thép",
   "matched_terms": ["HPG", "Hòa Phát"],
   "match_positions": [(123, 126), (200, 208)]},
  {"tier": 3, "ticker": "HSG", "sector": "Thép",
   "matched_terms": ["Hoa Sen"], ...}
]
```

Nếu không match T3/T2 → trả về 1 entity Tier 1:
```python
[{"tier": 1, "ticker": None, "sector": None, "matched_terms": ["FED", "lãi suất"]}]
```

### 3.2. Algorithm

```
def classify_tier(article):
    text = title + " " + summary + " " + content

    # Pass 1: match VN30 (longest-name-first, word-boundary cho ticker)
    company_matches = match_vn30(text)
    if company_matches:
        return [
            build_t3_entity(ticker, matched_terms, text)
            for ticker, matched_terms in company_matches.items()
        ]

    # Pass 2: match sector keywords
    sector_matches = match_sectors(text)
    if sector_matches:
        return [build_t2_entity(sector, matched_terms)
                for sector, matched_terms in sector_matches.items()]

    # Pass 3: fallback macro
    macro_terms = match_macro(text)
    return [build_t1_entity(matched_terms=macro_terms)]
```

### 3.3. Regex chi tiết

**Ticker** — bắt buộc word boundary để không match phụ:
```python
TICKER_RE = re.compile(
    r"(?<![A-Za-z0-9])(HPG|VIC|VHM|...)(?![A-Za-z0-9])"
)
```

**Tên công ty** — case-insensitive, ưu tiên dài trước:
```python
# Sort full_names theo length DESC để longest-match-first
patterns = sorted(all_names, key=len, reverse=True)
NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in patterns) + r")\b",
    re.IGNORECASE | re.UNICODE,
)
```

**Sector keyword** — match cụm:
```python
SECTOR_RES = {
    "Ngân hàng": re.compile(r"\b(ngành ngân hàng|tín dụng|NHNN|lãi suất cho vay|NIM)\b", re.I),
    "Thép":      re.compile(r"\b(ngành thép|HRC|thép xây dựng|giá thép)\b", re.I),
    ...
}
```

### 3.4. Heuristic chống false positive

- **Quá nhiều ticker (>5) + bài quá ngắn (<500 ký tự)** → có thể là bảng giá → skip toàn bộ T3, fallback T1.
- **Ticker xuất hiện chỉ 1 lần ở đoạn cuối** (sau từ "tham khảo:", "đọc thêm:") → bỏ.
- **Cụm "VICTORY", "Singapore GAS", "FPT Telecom"** vs "VIC", "GAS", "FPT" → blacklist các phrase nguy hiểm, kiểm tra char trước/sau khi match.

### 3.5. Unit test

File `tests/test_data/samples.csv` — denormalized, **1 row = 1 entity kỳ vọng**.
Bài nhắc nhiều ticker → nhiều row cùng `news_id`. Bài Tier 1 chỉ có 1 row, các cột ticker/sector để rỗng.

Schema:
```csv
news_id,content,expected_tier,expected_ticker,expected_sector
1,"HPG báo lãi kỷ lục Q4 nhờ giá thép tăng",3,HPG,Thép
2,"FED tăng lãi suất 25 điểm cơ bản",1,,
3,"Ngành ngân hàng Việt Nam ghi nhận tăng trưởng tín dụng",2,,Ngân hàng
4,"HPG hưởng lợi trong khi HSG áp lực biên lợi nhuận",3,HPG,Thép
4,"HPG hưởng lợi trong khi HSG áp lực biên lợi nhuận",3,HSG,Thép
```

Lưu ý CSV:
- `content` chứa dấu phẩy / newline → dùng `csv.writer` với `quoting=csv.QUOTE_MINIMAL`
- Loader đọc bằng `pandas.read_csv()` rồi `groupby("news_id")` để so sánh với output của classifier
- File loader đặt tại `tests/test_data/load_samples.py`

Test mục tiêu: precision ≥ 95% trên tập 20 bài.

---

## 4. Bước 3 — `classifier/snippet_extractor.py`

### 4.1. Mục đích

Cho 1 article + 1 entity → trả về 1-3 câu liên quan, ≤ 400 token.

### 4.2. Thuật toán

```
def extract_snippet(article, entity):
    sentences = split_into_sentences(article.content)
    # Tìm câu chứa entity (theo matched_terms hoặc match lại regex)
    hits = [i for i, s in enumerate(sentences) if entity_in(s, entity)]
    if not hits:
        return article.summary or article.title

    # Lấy [câu trước, câu chứa, câu sau] gom lại
    windows = set()
    for i in hits:
        windows.update([max(0, i-1), i, min(len(sentences)-1, i+1)])

    snippet = " ".join(sentences[j] for j in sorted(windows))
    return truncate_to_token_limit(snippet, max_tokens=400)
```

### 4.3. Tách câu tiếng Việt

Dùng regex đơn giản trước, không cần thư viện nặng:
```python
SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZĐÁÀÂ])")
```
Nếu cần chính xác hơn → `underthesea.sent_tokenize` (thư viện NLP Vietnamese).

Tôi đề xuất bắt đầu regex, nếu thấy snippet bị dính 2 câu thì mới thêm `underthesea`.

### 4.4. Edge case

- Bài quá ngắn (≤ 3 câu) → trả nguyên `summary` hoặc `title`.
- Entity chỉ xuất hiện trong title/summary → snippet = title + summary.

---

## 5. Bước 4 — `classifier/absa_mdeberta.py`

### 5.1. Model

```
model_name = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
```
(Đây là bản tốt hơn của `mDeBERTa-v3-base-xnli-multilingual`, FT thêm trên ANLI/FEVER. Vẫn 3 nhãn: entailment / neutral / contradiction.)

### 5.2. Cách dùng 3 nhãn — KHÁC code mẫu của bạn

Code mẫu của bạn lấy `probs[:, 0]` cho pos và neg riêng → cách này bỏ thông tin "neutral" và 2 score không cộng = 1.

**Cách đúng** — gom 3 hypothesis làm 3 candidate, lấy score entailment, softmax across 3:

```python
def absa_sentiment(snippet, entity_name, entity_type="company"):
    if entity_type == "company":
        hypotheses = [
            f"Sắc thái của bài viết đối với {entity_name} là tích cực, tốt đẹp.",
            f"Sắc thái của bài viết đối với {entity_name} là tiêu cực, xấu, đáng lo ngại.",
            f"Bài viết chỉ đề cập đến {entity_name} một cách trung lập, không có sắc thái rõ ràng.",
        ]
    elif entity_type == "sector":
        hypotheses = [
            f"Triển vọng của ngành {entity_name} là tích cực.",
            f"Triển vọng của ngành {entity_name} là tiêu cực.",
            f"Bài viết về ngành {entity_name} mang tính trung lập, chỉ thông tin.",
        ]
    elif entity_type == "macro":
        hypotheses = [
            "Tin tức vĩ mô này có ảnh hưởng tích cực đến thị trường chứng khoán Việt Nam.",
            "Tin tức vĩ mô này có ảnh hưởng tiêu cực đến thị trường chứng khoán Việt Nam.",
            "Tin tức này chỉ mang tính thông tin trung lập về kinh tế vĩ mô.",
        ]

    # Batch 3 cặp (premise, hypothesis)
    inputs = tokenizer(
        [snippet] * 3, hypotheses,
        padding=True, truncation=True, max_length=512, return_tensors="pt"
    )
    with torch.no_grad():
        logits = model(**inputs).logits      # shape [3, 3]
        # Lấy entailment prob của mỗi hypothesis
        # mDeBERTa label order: [entailment, neutral, contradiction]
        entail_probs = torch.softmax(logits, dim=-1)[:, 0]  # shape [3]
        # Softmax across 3 candidates để chuẩn hóa thành phân phối nhãn
        label_dist = torch.softmax(entail_probs, dim=0)     # shape [3]

    labels = ["positive", "negative", "neutral"]
    idx = label_dist.argmax().item()

    return {
        "label": labels[idx],
        "confidence": label_dist[idx].item(),
        "sentiment_score": (label_dist[0] - label_dist[1]).item(),  # ∈ [-1, 1]
        "probs": dict(zip(labels, label_dist.tolist())),
    }
```

### 5.3. Batch nhiều entity cùng lúc

Pipeline thực tế có hàng nghìn bài × nhiều entity. Code thật sẽ batch:

```python
# Gom toàn bộ (snippet, hypothesis) thành 1 batch lớn (vd 32 cặp)
# Tokenize 1 phát, forward 1 phát, slice lại theo entity
```

Tốc độ: trên GPU T4 ~50 cặp/s, CPU ~3 cặp/s. Bạn cần xác nhận có GPU không.

### 5.4. Multi-entity ABSA (1 câu nhắc nhiều mã)

Code mẫu của bạn xử lý đúng — gọi `absa_sentiment(snippet, "Hòa Phát")` rồi `absa_sentiment(snippet, "Hoa Sen")` trên CÙNG snippet. Đây là điểm mạnh của NLI-based ABSA: model học được "tích cực với X nhưng tiêu cực với Y" vì hypothesis nêu rõ entity.

### 5.5. Kiểm chứng

Sau khi chạy module này, tôi sẽ test 5 câu có chuyên gia / bạn tự đánh giá:
1. "HPG báo lãi kỷ lục Q4." → HPG positive
2. "VHM gặp khó với dự án bị thanh tra." → VHM negative
3. "HPG hưởng lợi từ giá thép tăng, trong khi HSG áp lực biên lợi nhuận." → HPG pos, HSG neg
4. "VN-Index đóng cửa giảm 15 điểm do áp lực bán mạnh." → T1 negative
5. "Ngân hàng Nhà nước giữ nguyên lãi suất điều hành." → T1 neutral

---

## 6. Bước 5 — `classify_news.py` (entrypoint)

### 6.1. CLI

```
cd test/news_classifier
python classify_news.py \
  --content-csv ../../stocknewscrawl/vnstocknewsdata/news_content.csv \
  --links-csv   ../../stocknewscrawl/vnstocknewsdata/news_links.csv \
  --output-csv  ../../stocknewscrawl/vnstocknewsdata/news_labels.csv \
  --batch-size  16 \
  --device      cuda          # or cpu
  --resume                    # bỏ qua news_id đã có trong output
```

### 6.2. Flow

```
load vn30_companies, sectors, macro_keywords
load model + tokenizer (1 lần)
load done_news_ids từ output (resume)

for each news in news_content (join với news_links):
    if news_id in done_news_ids: continue

    entities = tier_classifier.classify_tier(news)
    for ent in entities:
        snippet = snippet_extractor.extract_snippet(news, ent)
        sent = absa_mdeberta.absa_sentiment(snippet, ent_name, ent_type)
        write_row(news_id, ent, sent, snippet)
```

### 6.3. Batching để tăng tốc

Thay vì gọi model 1 entity/lần, gom batch:
```
collect (snippet, hypotheses) cho 16 entity → tokenize 1 lần → forward 1 lần
→ slice kết quả về từng entity
```

Lưu kết quả ngay sau mỗi batch (không buffer trong RAM) để có thể resume.

### 6.4. Logging

In mỗi 100 bài: số bài đã xử lý, phân phối Tier (T1/T2/T3), throughput.

---

## 7. Bước 6 — Validation

### 7.1. Gold set

Tự đánh nhãn 100 bài random từ `news_content.csv` (bạn + tôi cùng làm):
- Tier (1/2/3)
- Nếu T3: list ticker + label per ticker
- Nếu T2: sector + label
- Nếu T1: label

Format `tests/gold_100.csv` — denormalized, **1 row = 1 entity** (giống schema output của classifier):
```csv
news_id,gold_tier,gold_ticker,gold_sector,gold_label
42,3,HPG,Thép,positive
55,3,HPG,Thép,positive
55,3,HSG,Thép,negative
73,2,,Ngân hàng,positive
91,1,,,negative
```

Lưu ý:
- 1 `news_id` xuất hiện nhiều lần nếu bài nhắc nhiều entity (group key = `news_id`)
- Cột ticker rỗng nếu tier ≠ 3, sector rỗng nếu tier = 1
- Đánh nhãn trực tiếp bằng Excel/Google Sheets → export CSV (tiện hơn JSON)
- Loader script `tests/load_gold.py`: `pd.read_csv(...).groupby("news_id")` để map về dạng nested cho việc so sánh metric

### 7.2. Metric

| Cấp | Metric | Mục tiêu pass |
|---|---|---|
| Tier classification | Accuracy | ≥ 90% |
| Ticker extraction (T3) | Precision / Recall | P ≥ 95%, R ≥ 85% |
| Sentiment (per entity) | Accuracy 3-class | ≥ 70% |
| Sentiment per direction (pos vs neg) | F1 | ≥ 75% |

70% accuracy 3-class với zero-shot mDeBERTa là baseline thực tế cho tiếng Việt; nếu thấp hơn cần xem lại hypothesis template.

### 7.3. Lỗi điển hình cần báo cáo

Sau khi chạy gold set, output table:
```
| news_id | gold        | predicted   | reason            |
| 17      | HPG pos     | HPG neutral | snippet thiếu ngữ cảnh |
| 23      | T1 neg      | T3 VCB neg  | over-attribution  |
```

---

## 8. Schema CSV output đầy đủ

File `vnstocknewsdata/news_labels.csv`:

```csv
id,news_id,tier,ticker,sector,label,sentiment_score,confidence,extract,aspect,published_at,method,rule_matched_terms,created_at
1,42,3,HPG,Thép,positive,0.78,0.85,"Hòa Phát báo lãi kỷ lục Q4 nhờ giá thép tăng...",,2026-04-13T08:30:00,rule+nli,"HPG;Hòa Phát",2026-05-21T22:30:00
2,42,3,HSG,Thép,negative,-0.65,0.71,"...trong khi Hoa Sen gặp áp lực biên lợi nhuận.",,2026-04-13T08:30:00,rule+nli,"Hoa Sen;HSG",2026-05-21T22:30:00
3,91,1,,,negative,-0.45,0.62,"FED nâng lãi suất...",,2026-04-12T15:00:00,rule+nli,"FED;lãi suất",2026-05-21T22:30:00
```

Lưu ý:
- 1 bài có thể có nhiều row (mỗi entity 1 row).
- `ticker` rỗng khi tier ≠ 3.
- `sector` rỗng khi tier = 1.
- `sentiment_score` = P(pos) − P(neg), nằm [-1, 1].
- `aspect` để rỗng ở pass 1, có thể extract sau bằng từ điển aspect.

---

## 9. Dependencies dự kiến

`news_classifier/requirements.txt`:
```
transformers>=4.36
torch>=2.0
pyyaml
tqdm
pandas
scikit-learn        # TF-IDF cho Bước 1.5
pyvi                # word segmentation tiếng Việt cho TF-IDF
# optional:
# underthesea       (Vietnamese sentence splitting, nếu regex không đủ)
# sentencepiece     (đi kèm mDeBERTa tokenizer)
```

Model size mDeBERTa-v3-base ≈ 280 MB, tải về `~/.cache/huggingface/` lần đầu chạy.

---

## 10. Lịch trình đề xuất

| Bước | Thời gian | Phụ thuộc |
|---|---|---|
| 1. Soạn `vn30_companies.yml` | 1-2 giờ (thủ công, kỹ) | — |
| **1.5. `build_sector_keywords.py` (TF-IDF)** | **1.5-2 giờ code + ~10 phút bạn duyệt draft** | bước 1 + news_content.csv |
| 2. `tier_classifier.py` + test | 2-3 giờ | bước 1, 1.5 |
| 3. `snippet_extractor.py` | 1 giờ | — |
| 4. `absa_mdeberta.py` | 2-3 giờ (test trên sample) | — |
| 5. `classify_news.py` (orchestrator) | 1-2 giờ | 2, 3, 4 |
| 6. Gold set + validation | 3-4 giờ (đánh nhãn 100 bài) | 5 |
| **Tổng** | **~14-18 giờ** | |

---

## 11. Những câu hỏi cần bạn quyết trước khi tôi code

### Q1. Phạm vi VN30 hay mở rộng?
- Chỉ 30 mã VN30, hay thêm các mã hay xuất hiện trong báo (HSG, NVL, DXG…)?
- Đề xuất tôi: chỉ VN30 ở v1 (đúng yêu cầu của bạn). v2 mở rộng.

### Q2. Sentence splitter
- Regex đơn giản hay `underthesea` ngay từ đầu?
- Đề xuất: regex trước, dependency tối thiểu.

### Q3. Device
- Có GPU không? Nếu chỉ CPU, mỗi entity ~0.3s → 10000 bài × 2 entity TB → ~100 phút.
- Nếu có GPU T4/RTX → ~10 phút.

### Q4. Aspect extraction
- v1 để rỗng, hay tôi làm luôn pass-2 trích aspect bằng từ điển?
- Đề xuất: v1 rỗng. Aspect chiếm thêm 30% effort mà gold set 100 bài chưa đủ validate.

### Q5. Hành xử với bài tiếng Anh
- Có bài tiếng Anh không (vd VnEconomy English section)? mDeBERTa multilingual chịu được nhưng hypothesis của tôi soạn bằng tiếng Việt.
- Đề xuất: chỉ xử lý bài tiếng Việt; detect bằng tỷ lệ ký tự có dấu, < threshold → skip.

### Q6. Resume / incremental
- Khi crawler thêm bài mới, classifier có nên rerun toàn bộ không?
- Đề xuất: dùng `--resume` skip `news_id` đã có; chỉ rerun nếu thay đổi từ điển.

### Q7. Ngưỡng confidence
- Có cần loại bài confidence < 0.5 ra khỏi output không? Hay vẫn lưu nhưng đánh dấu?
- Đề xuất: vẫn lưu, để dashboard tự filter; field `confidence` đã có sẵn.

---

## 12. Sau khi bạn duyệt plan này

Tôi sẽ làm theo đúng thứ tự bước 1 → 6, **mỗi bước xong sẽ commit + báo cáo** để bạn kiểm tra trước khi sang bước tiếp.

Nếu có bước nào bạn muốn tôi thay đổi (vd bỏ snippet, dùng full content), nói trước khi bắt đầu để tránh phải refactor.
