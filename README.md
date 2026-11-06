# American Options on Brent (FE 620)

Prices American options on **BNO**, the United States Brent Oil Fund (an ETF), with a
binomial tree. Black-Scholes is the European cross-check. Run steps are in
[docs/QUICKSTART.md](docs/QUICKSTART.md).

## Architecture

    yfinance ─► scripts/snapshot.py ─► data/snapshots/<date>/ ─► scripts/price_snapshot.py ─► reports/<date>_pricing.xlsx
                 (network)              (frozen inputs)            (offline)

Two stages keep the numbers reproducible. The network stage saves a frozen snapshot,
and the analysis stage reads only that snapshot.

## Modules

| File | Role |
|---|---|
| `src/aoo/data.py` | Snapshot layout (`UNDERLYING`, `RATE`, `SNAP_DIR`) and the offline loader |
| `src/aoo/vol.py` | Historical volatility: √252 × stdev of daily log returns, with its standard error |
| `src/aoo/tree.py` | Cox-Ross-Rubinstein binomial tree (American or European, dividend yield q) and implied vol |
| `src/aoo/bs.py` | Black-Scholes European price, the closed-form check on the tree |
| `src/aoo/lsm.py` | Longstaff-Schwartz Monte Carlo for American options (GBM paths, cubic regression) |
| `src/aoo/validation.py` | Textbook reference values (Hull), shared by the tests and the Checks sheet |
| `src/aoo/report.py` | Excel layout only: sheets, formulas, colours, charts |
| `scripts/snapshot.py` | Saves BNO option chains, BNO closes and T-bill closes for today |
| `scripts/price_snapshot.py` | Cleans quotes, prices them, solves implied vol, runs checks, writes the workbook |
| `tests/test_pricers.py` | Correctness tests |

## Modelling choices

- **Underlying:** BNO shares, treated as a stock with dividend yield q = 0. This is not
  Brent crude or Brent futures, so the futures risk-neutral probability does not apply.
- **Tree probability:** p = (e^((r−q)Δt) − d) / (u − d), with u = e^(σ√Δt) and d = 1/u.
- **Rate:** 13-week T-bill (`^IRX`) divided by 100.
- **Time:** business days / 252 (trading-day convention).
- **Volatility:** 6m / 3m / 1m lookbacks of 126 / 63 / 21 trading days; the tree uses 3m.
- **Smile and surface:** out-of-the-money quotes only (puts below spot, calls above).

## Validation reference points

| Check | Reference | Tolerance | Where |
|---|---|---|---|
| Black-Scholes | Textbook S=K=100, T=1, r=5%, σ=20%: call 10.4506, put 5.5735 | 1e-4 | tests |
| Hull: American put (S=K=50, r=10%, σ=40%, T=5m) | n=5 4.49, n=30 4.263, n=50 4.272, n=100 4.278, n=500 4.283 | 0.005 | tests, Checks sheet |
| Hull: Black-Scholes (S=42, K=40, r=10%, σ=20%, T=6m) | call 4.76, put 0.81 | 0.005 | tests, Checks sheet |
| Tree → Black-Scholes | European tree vs BS as n grows | 0.001 at n=4000 | tests, Checks sheet |
| American call = European call | No dividend, so early exercise is never optimal | 1e-6 | tests |
| American put ≥ European put and ≥ intrinsic | Holds for any n | strict | tests |
| Put-call parity (European BS) | C − P = S − K·e^(−rT) | 1e-9 | tests |
| LSM put vs tree | Hull put, 50 exercise dates, 100,000 paths | 3 s.e. + 0.01 | tests, Monte Carlo sheet |
| LSM call vs Black-Scholes | No dividend, so the American call is European | 3 s.e. | tests |
| Implied vol | Tree price at a known σ solves back to that σ; NaN at or below intrinsic | 1e-6 | tests |
| Historical vol | Known alternating returns | relative 1e-10 | tests |
| Put-call bounds on market mids | S − K < C − P < S − K·e^(−rT) | reported, not enforced | Checks sheet |

Tree convergence is not monotone. The error oscillates in n, so validate at large n.

## Output: `reports/<date>_pricing.xlsx`

Colour code: blue = input or value from Python, black = formula, green = link to another sheet.

| Sheet | Contents |
|---|---|
| Inputs | Spot, rate, dividend yield, the three historical volatilities, tree settings, data counts |
| Quotes | One row per cleaned quote: bid, ask, mid, tree and BS prices, model − mid, implied vol |
| Smile | OTM implied vol against K/S for the three nearest expiries, with a chart and historical σ |
| Surface | OTM implied vol by strike × expiry, colour-scaled; interpolated K/S grid with a 3D surface chart |
| Tree | Stock and put lattice for an ATM put (early exercise shaded); price vs steps chart |
| Monte Carlo | LSM vs tree vs Black-Scholes; LSM vs paths with ±2 s.e. band; 20 sample paths |
| Checks | Hull textbook values, put-call bound pass rates |

## Not built yet

Delta-hedging backtest, final report. LSM prices one illustrative contract; the quotes are priced with the tree.
