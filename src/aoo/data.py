"""Snapshot layout and offline loader. scripts/snapshot.py writes it; analysis reads it."""

import json
from pathlib import Path

import pandas as pd

# United States Brent Oil Fund: the only Brent-linked symbol with options on Yahoo.
UNDERLYING = "BNO"
# 13-week T-bill yield, quoted in percent.
RATE = "^IRX"

SNAP_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshots"


def load_snapshot(name: str | None = None) -> dict:
    """Load data/snapshots/<name> (default: latest). No network access."""
    if name is None:
        dirs = sorted(p.name for p in SNAP_DIR.glob("*") if p.is_dir())
        if not dirs:
            raise FileNotFoundError(f"No snapshots in {SNAP_DIR}; run scripts/snapshot.py first")
        name = dirs[-1]
    folder = SNAP_DIR / name

    def close(file: str) -> pd.Series:
        s = pd.read_csv(folder / file, index_col=0)["Close"]
        s.index = pd.to_datetime(s.index)
        return s

    return {
        "meta": json.loads((folder / "meta.json").read_text()),
        "underlying": close("underlying.csv"),
        "rate": close("irx.csv"),
        "chains": pd.read_csv(folder / "chains.csv"),
    }
