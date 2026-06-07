"""
supabase_client.py — Shared Supabase client + helper functions.

Provides:
  - `sb` : Supabase client instance
  - `upsert_batch()` : Batch upsert with conflict handling
  - `log_pipeline_run()` : Insert pipeline_run_logs entry
  - `upload_to_bucket()` : Upload file to Storage bucket
  - `ensure_buckets()` : Create buckets if they don't exist
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from supabase import create_client

from pipeline.config import (
    SUPABASE_URL, SUPABASE_KEY,
    BUCKET_RAW_NEWS, BUCKET_RAW_PRICES,
    BUCKET_RAW_SENTIMENT, BUCKET_ML_ARTIFACTS,
    BATCH_SIZE,
)

# ── Client singleton ──────────────────────────────────────────────────
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Bucket management ─────────────────────────────────────────────────

ALL_BUCKETS = [BUCKET_RAW_NEWS, BUCKET_RAW_PRICES, BUCKET_RAW_SENTIMENT, BUCKET_ML_ARTIFACTS]


def ensure_buckets():
    """Create all storage buckets if they don't exist."""
    existing = {b.name for b in sb.storage.list_buckets()}
    for name in ALL_BUCKETS:
        if name not in existing:
            try:
                sb.storage.create_bucket(name, options={"public": False})
                print(f"  ✅ Bucket created: {name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    pass
                else:
                    print(f"  ⚠️  Bucket {name}: {e}")
        else:
            print(f"  ✓ Bucket exists: {name}")


def upload_to_bucket(bucket: str, remote_path: str, local_path: str | Path,
                     content_type: str = "application/octet-stream") -> bool:
    """Upload a file to Supabase Storage. Returns True on success."""
    local_path = Path(local_path)
    if not local_path.exists():
        print(f"  ❌ File not found: {local_path}")
        return False

    try:
        with open(local_path, "rb") as f:
            data = f.read()

        # Remove existing file if present (upsert semantics)
        try:
            sb.storage.from_(bucket).remove([remote_path])
        except Exception:
            pass

        sb.storage.from_(bucket).upload(
            path=remote_path,
            file=data,
            file_options={"content-type": content_type},
        )
        size_mb = len(data) / (1024 * 1024)
        print(f"  ✅ Uploaded {local_path.name} → {bucket}/{remote_path} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"  ❌ Upload failed {local_path.name}: {e}")
        return False


# ── Database helpers ───────────────────────────────────────────────────

def upsert_batch(table: str, rows: list[dict], on_conflict: str = "",
                 batch_size: int = BATCH_SIZE) -> int:
    """
    Upsert rows into a table in batches.
    Returns total number of rows successfully upserted.
    """
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            q = sb.table(table).upsert(batch, on_conflict=on_conflict)
            q.execute()
            total += len(batch)
        except Exception as e:
            print(f"  ⚠️  Batch {i//batch_size + 1} failed on {table}: {e}")
            # Try row-by-row for failed batch
            for row in batch:
                try:
                    sb.table(table).upsert(row, on_conflict=on_conflict).execute()
                    total += 1
                except Exception:
                    pass
    return total


def insert_batch(table: str, rows: list[dict], batch_size: int = BATCH_SIZE) -> int:
    """Insert rows (no upsert). Skips duplicates silently."""
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            sb.table(table).insert(batch).execute()
            total += len(batch)
        except Exception as e:
            err = str(e).lower()
            if "duplicate" in err or "unique" in err or "conflict" in err:
                # Try one by one
                for row in batch:
                    try:
                        sb.table(table).insert(row).execute()
                        total += 1
                    except Exception:
                        pass
            else:
                print(f"  ⚠️  Insert batch failed on {table}: {e}")
    return total


def log_pipeline_run(run_type: str, status: str = "running",
                     source: str = None, symbol: str = None,
                     metadata: dict = None) -> int | None:
    """Insert a pipeline_run_logs entry and return its id."""
    row = {
        "run_type": run_type,
        "status": status,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if source:
        row["source"] = source
    if symbol:
        row["symbol"] = symbol
    if metadata:
        row["metadata"] = json.dumps(metadata)
    try:
        res = sb.table("pipeline_run_logs").insert(row).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        print(f"  ⚠️  Log failed: {e}")
    return None


def update_pipeline_run(run_id: int, status: str, records_processed: int = 0,
                        records_failed: int = 0, error_message: str = None):
    """Update an existing pipeline_run_logs entry."""
    row = {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "records_processed": records_processed,
        "records_failed": records_failed,
    }
    if error_message:
        row["error_message"] = error_message
    try:
        sb.table("pipeline_run_logs").update(row).eq("id", run_id).execute()
    except Exception as e:
        print(f"  ⚠️  Update log failed: {e}")
