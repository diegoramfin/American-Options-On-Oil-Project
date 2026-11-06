"""Freeze today's Yahoo Finance data into data/snapshots/<YYYY-MM-DD>/ (needs network).

Yahoo only serves the current option chain, so a "historical date" means a snapshot saved
on that day. Rerunning on the same day overwrites that day's folder.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aoo.data import RATE, SNAP_DIR, UNDERLYING  # noqa: E402


def save_close(symbol: str, period: str, path: Path) -> pd.Series:
    history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    close = pd.Series(history["Close"].to_numpy(), index=history.index.strftime("%Y-%m-%d"))
    close.rename_axis("Date").rename("Close").to_csv(path)
    return close


def pull_chains(symbol: str) -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    frames = []
    for expiry in ticker.options:
        chain = ticker.option_chain(expiry)
        for kind, df in (("call", chain.calls), ("put", chain.puts)):
            frames.append(df.assign(expiry=expiry, kind=kind))
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    snap_date = datetime.now().strftime("%Y-%m-%d")
    out = SNAP_DIR / snap_date
    out.mkdir(parents=True, exist_ok=True)

    close = save_close(UNDERLYING, "2y", out / "underlying.csv")
    save_close(RATE, "3mo", out / "irx.csv")
    chains = pull_chains(UNDERLYING)
    chains.to_csv(out / "chains.csv", index=False)
    meta = {
        "pulled_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": snap_date,
        "underlying": UNDERLYING,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"Saved {out}")
    print(f"{UNDERLYING} close {close.iloc[-1]:.2f} on {close.index[-1]}")
    print(f"{len(chains)} option rows")


if __name__ == "__main__":
    main()
