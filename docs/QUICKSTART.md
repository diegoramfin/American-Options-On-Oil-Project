# Quick start: American options on BNO

Prices American options on **BNO** (United States Brent Oil Fund, an ETF) with a
binomial tree, checks it against Black-Scholes, and compares model prices with
market mids. Architecture and modules are in the [README](../README.md).

Run every command from the project root.

## Setup (once)

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## Run

    python scripts/snapshot.py          # 1. freeze market data (needs internet)
    python scripts/price_snapshot.py    # 2. price the latest snapshot (offline)
    python -m pytest -q                 # 3. correctness tests (offline)
    black src scripts tests             # format before committing

- Step 1 writes `data/snapshots/<YYYY-MM-DD>/`. Rerunning it on the same day
  **overwrites** that folder. Copy the folder first if you need to keep it.
- Step 2 reads the latest snapshot (or `python scripts/price_snapshot.py 2026-11-06`
  for a specific one) and writes `reports/<date>_pricing.xlsx`. It takes about 40 seconds.
- Step 3 should show all tests passing.

Yahoo only serves the **current** option chain. A "historical date" in this
project means a saved snapshot, not a past chain.

## What needs review

1. **Underlying.** We price options on the BNO ETF shares, not on Brent crude or
   Brent futures. The model treats BNO as a stock with no dividend (q = 0). Confirm
   BNO has made no distributions over the sample period.
2. **Historical options data.** Yahoo gives no past chains, and no free source has
   been verified. Decide how the team gets past chains, or accept snapshots only.
3. **Quote quality.** About a third of put-call pairs fail the American bounds
   (S − K < C − P < S − K·e^(−rT)), mostly on the shortest expiries. See the Checks
   sheet. Decide the cleaning rule before relying on the smile or the market comparison.
4. **Snapshot timing.** The 2026-11-06 snapshot was pulled at 12:19 ET with the
   market open, so S is an intraday price taken at the same moment as the quotes, and
   the last daily return is a partial day. Pulling after 4 pm ET gives a true close,
   but quotes may then be stale or zero. Agree on a pull time for the frozen date.
5. **Risk-free rate.** We use the 13-week T-bill from Yahoo (`^IRX`). Check whether
   the team prefers a different source, such as FRED.
6. **Tree settings.** 100 steps per contract. The Checks sheet shows the convergence;
   decide whether 100 is enough for the comparison you need.
7. **Test tolerances.** The Hull checks allow 0.005 because Hull prints two or three
   decimals; our values match every printed digit. Confirm that tolerance is acceptable.
8. **Not built yet.** The hedging backtest and the final report. LSM currently prices
   one illustrative ATM put; the quote table is priced with the tree.
