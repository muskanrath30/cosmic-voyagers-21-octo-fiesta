"""
Fetch the real datasets and reduce them to local training samples.

    python -m manufacturing.fetch_datasets [--rows 20000]

  * MetroPT-3 (UCI 791, real metro compressor)  -> data/samples/metropt_sample.csv
  * CWRU bearing (.mat, real lab rig)           -> data/samples/cwru_sample.npz
  * NASA C-MAPSS FD001 is bundled. For FD002-FD004 put the NASA train files at
    data/samples/train_FD002.txt etc.; training picks them up automatically.
  * AI4I 2020 (optional legacy asset): python download_dataset.py

MetroPT-3 sampling keeps ALL anomaly rows (up to one third of --rows) plus a
random sample of normal rows, sorted by time, so failures are not lost to
down-sampling. The full 1.5M-row file can be loaded into BigQuery with
ingest_to_bigquery.py --full-metropt <csv>.

If a download is blocked the script says so and the package keeps running on
synthetic stand-ins; metrics.json records data_source so this is never hidden.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SAMPLE_DIR = Path(__file__).resolve().parent / "data" / "samples"

METROPT_URLS = [
    "https://archive.ics.uci.edu/static/public/791/metropt+3+dataset.zip",
]
# documented MetroPT-3 failure windows (start, end) -> anomaly label
METROPT_FAILURES = [
    ("2020-04-18 00:00:00", "2020-04-18 23:59:00"),
    ("2020-05-29 23:30:00", "2020-05-30 06:00:00"),
    ("2020-06-05 10:00:00", "2020-06-07 14:30:00"),
    ("2020-07-15 14:30:00", "2020-07-15 19:00:00"),
]
CWRU_BASE = "https://zenodo.org/records/10986655/files/{name}?download=1"
# 97/98 normal; 105 inner race, 130 ball, 169 outer race (drive end, 12 kHz)
CWRU_FILES = {"97.mat": 0, "98.mat": 0, "105.mat": 1, "130.mat": 1, "169.mat": 1}
CWRU_WINDOW = 2048


def _download(url: str, timeout: int = 300) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pm-copilot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  ! download failed ({url}): {exc}")
        return None


def label_metropt(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"DV_eletric": "DV_electric"})  # UCI column typo
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    mask = pd.Series(False, index=df.index)
    for start, end in METROPT_FAILURES:
        mask |= df["timestamp"].between(pd.Timestamp(start), pd.Timestamp(end))
    df["anomaly"] = mask.astype(int)
    return df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])


def sample_metropt(df: pd.DataFrame, rows: int) -> pd.DataFrame:
    pos = df[df["anomaly"] == 1]
    neg = df[df["anomaly"] == 0]
    n_pos = min(len(pos), rows // 3)
    out = pd.concat([
        pos.sample(n_pos, random_state=42),
        neg.sample(min(len(neg), rows - n_pos), random_state=42),
    ])
    return out.sort_values("timestamp")


def fetch_metropt(rows: int) -> bool:
    print("[metropt] downloading MetroPT-3 (about 200 MB) ...")
    raw = next((r for r in (_download(u) for u in METROPT_URLS) if r), None)
    if not raw:
        print("[metropt] FAILED. Manual: download the MetroPT-3 CSV from "
              "https://archive.ics.uci.edu/dataset/791 and run:\n"
              "    python -m manufacturing.fetch_datasets --metropt-csv <file.csv>")
        return False
    try:
        if raw[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(raw))
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            df = pd.read_csv(zf.open(name))
        else:
            df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        print(f"[metropt] parse failed: {exc}")
        return False
    return _save_metropt(df, rows)


def _save_metropt(df: pd.DataFrame, rows: int) -> bool:
    df = label_metropt(df)
    sample = sample_metropt(df, rows)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    sample.to_csv(SAMPLE_DIR / "metropt_sample.csv", index=False)
    print(f"[metropt] full={len(df)} rows, anomalies={int(df['anomaly'].sum())}; "
          f"wrote {len(sample)} rows -> metropt_sample.csv")
    return True


def _stats(signal: np.ndarray) -> list[float]:
    signal = np.asarray(signal, dtype=float).ravel()
    rms = float(np.sqrt(np.mean(signal ** 2)))
    peak = float(np.max(np.abs(signal)))
    mean, std = float(np.mean(signal)), float(np.std(signal)) or 1e-9
    return [rms, float(np.mean(((signal - mean) / std) ** 4)),
            float(np.mean(((signal - mean) / std) ** 3)), peak, peak / (rms or 1e-9)]


def fetch_cwru() -> bool:
    print("[cwru] downloading CWRU .mat files ...")
    try:
        from scipy.io import loadmat
    except ImportError:
        print("[cwru] scipy not installed; skipping")
        return False

    X, y, src = [], [], []
    for file_index, (name, label) in enumerate(CWRU_FILES.items()):
        raw = _download(CWRU_BASE.format(name=name))
        if not raw:
            continue
        try:
            mat = loadmat(io.BytesIO(raw))
            de = next((v for k, v in mat.items() if k.endswith("DE_time")), None)
            fe = next((v for k, v in mat.items() if k.endswith("FE_time")), None)
            if de is None:
                print(f"  ! {name}: no drive-end signal")
                continue
            de = np.asarray(de).ravel()
            fe = np.asarray(fe).ravel() if fe is not None else de
            n = min(len(de), len(fe))
            for start in range(0, n - CWRU_WINDOW, CWRU_WINDOW):
                X.append(_stats(de[start:start + CWRU_WINDOW])
                         + _stats(fe[start:start + CWRU_WINDOW]))
                y.append(label)
                src.append(file_index)
        except Exception as exc:
            print(f"  ! {name}: {exc}")

    if not X or len(set(y)) < 2:
        print("[cwru] FAILED (need both normal and fault files). Manual: download "
              "the CWRU .mat files and place them in a folder, then adapt CWRU_FILES.")
        return False

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(SAMPLE_DIR / "cwru_sample.npz",
             X=np.array(X), y=np.array(y), src=np.array(src))
    print(f"[cwru] wrote {len(X)} windows from {len(set(src))} files -> cwru_sample.npz")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows", type=int, default=20000)
    ap.add_argument("--metropt-csv", help="use a MetroPT-3 CSV you downloaded yourself")
    args = ap.parse_args()

    if args.metropt_csv:
        ok = _save_metropt(pd.read_csv(args.metropt_csv), args.rows)
    else:
        ok = fetch_metropt(args.rows)
    ok = fetch_cwru() and ok

    print("\nNext: python -m manufacturing.train")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
