# American Options on Brent (FE 620)

Prices American options on **BNO** (United States Brent Oil Fund, an ETF, and the only
Brent-linked underlying with options on Yahoo Finance) in the Black-Scholes model.
Longstaff-Schwartz Monte Carlo (LSM) is the main pricer; a binomial tree confirms it.

## Quick start

Run from the project root.

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

    python scripts/snapshot.py         # freeze today's market data (internet)
    python scripts/price_snapshot.py   # price the latest snapshot, offline (~2.5 min)
    python -m pytest -q                # validation tests (~15 s)
    black src scripts tests            # format before committing

- `snapshot.py` writes `data/snapshots/<YYYY-MM-DD>/` and overwrites that day's folder.
- `price_snapshot.py` writes `reports/<date>_pricing.xlsx`. Pass a date to price an older
  snapshot: `python scripts/price_snapshot.py 2026-11-06`.
- Yahoo serves only the current option chain, so a historical date means a saved snapshot.

## Architecture

    yfinance ─► scripts/snapshot.py ─► data/snapshots/<date>/ ─► scripts/price_snapshot.py ─► reports/<date>_pricing.xlsx
                 (network)              (frozen inputs)            (offline)

| Module | Role |
|---|---|
| `src/aoo/data.py` | Snapshot layout and offline loader |
| `src/aoo/vol.py` | Historical volatility (6m / 3m / 1m lookbacks) |
| `src/aoo/bs.py` | Black-Scholes European price |
| `src/aoo/tree.py` | Binomial tree: confirmation pricer, lattice, implied vol |
| `src/aoo/lsm.py` | Main pricer: LSM with a Black-Scholes control variate |
| `src/aoo/validation.py` | Dummy-data and textbook (Hull) validation cases |
| `src/aoo/report.py` | Excel layout only |
| `scripts/price_snapshot.py` | The pipeline: clean quotes, price, validate, write the workbook |
| `tests/test_pricers.py` | Automated validation |

Each model module's docstring states its assumptions and formulas.

## Pricing engine

One model, Black-Scholes (GBM, constant r, q and σ), solved three ways:

| Role | Method |
|---|---|
| Main price | LSM: 20,000 paths per expiry shared by its strikes, daily exercise up to 50 dates |
| Confirmation | Binomial tree, one time step per business day (at least 100); confirmed when \|LSM − tree\| ≤ 2 s.e. + $0.01 |
| Implied vol | Solved on the tree (root-finding needs a smooth price; LSM is noisy) |
| Closed form | Black-Scholes: LSM's paths and control variate; exact for calls when q = 0; American − BS = early-exercise premium |

Inputs: BNO price at the pull, 13-week T-bill (`^IRX`) for r, q = 0, σ from a 3-month lookback,
time in business days / 252.

## Validation

Lives in `tests/test_pricers.py` (pass/fail), `src/aoo/validation.py` (cases and reference
values) and the workbook's Validation sheet (for the report):

- Dummy data (S = K = 100, T = 1, r = 5%, σ = 20%): Black-Scholes benchmark, tree vs
  Black-Scholes, and an American call with an 8% dividend where early exercise appears.
- Hull textbook values for the tree and Black-Scholes, matched to every printed digit.
- On market data: LSM confirmed by the tree per quote, and put-call bounds on the quotes.

## Workbook

`Inputs` · `Quotes` (every quote, all methods) · `Smile` · `Surface` (heatmap and 3D chart) ·
`Tree` (lattice and convergence) · `Monte Carlo` (LSM study and sample paths) · `Validation`.
Blue = input, black = formula, green = link to another sheet.

Open review items: [docs/REVIEW.md](docs/REVIEW.md).
