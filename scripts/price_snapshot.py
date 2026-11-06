"""Price BNO options on a frozen snapshot (default: latest) and write the Excel report.

Offline: reads data/snapshots/<date>/ only. Writes reports/<date>_pricing.xlsx.
Usage: python scripts/price_snapshot.py [YYYY-MM-DD]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from aoo.bs import bs_price  # noqa: E402
from aoo.data import load_snapshot  # noqa: E402
from aoo.lsm import lsm_on_paths, lsm_price, simulate_paths  # noqa: E402
from aoo.report import PricingRun, write_report  # noqa: E402
from aoo.tree import implied_vol, tree_lattice, tree_price  # noqa: E402
from aoo.validation import dividend_call_lattice, validation_sections  # noqa: E402
from aoo.vol import TRADING_DAYS, WINDOWS, hist_vol  # noqa: E402

# Main pricer: LSM. Confirmation and implied vol: the binomial tree.
LSM_PATHS_PER_EXPIRY = 20_000
MAX_EXERCISE_DATES = 50  # daily exercise up to this cap; beyond it LSM prices a Bermudan
CONFIRM_TOLERANCE = 0.01  # one price tick: confirmed when |LSM - tree| <= 2 s.e. + this
MIN_TREE_STEPS = 100  # tree: one step per business day, at least this many
BASE_WINDOW = "3m"  # balances estimation error (short windows) against stale regimes (long)
MAX_SPREAD = 0.5  # drop quotes whose (ask - bid) / mid exceeds this
SURFACE_GRID = np.round(np.arange(0.875, 1.2501, 0.025), 3)  # K / S grid for the 3D chart

# Illustrative at-the-money put (Tree and Monte Carlo sheets).
LATTICE_STEPS = 6  # small enough to read on a sheet
CONVERGENCE_STEPS = tuple(range(10, 301, 10))
BENCHMARK_STEPS = 500
LSM_PATHS = (1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000)
SHOWN_PATHS = 20

BAR = "{desc} {percentage:3.0f}%|{bar:30}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]"


def stage(message: str) -> None:
    print(f"\n▸ {message}", flush=True)


def progress(items=None, desc: str = "", total: int | None = None):
    return tqdm(items, desc=f"  {desc:<30}", total=total, bar_format=BAR)


def clean(chains: pd.DataFrame, val_date: pd.Timestamp) -> pd.DataFrame:
    """Keep live two-sided quotes with a reasonable spread; add mid and T (business days / 252)."""
    df = chains.assign(expiry=pd.to_datetime(chains["expiry"]))
    df = df[(df["expiry"] > val_date) & (df["bid"] > 0) & (df["ask"] > df["bid"])].copy()
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df = df[(df["ask"] - df["bid"]) / df["mid"] <= MAX_SPREAD].copy()
    df["T"] = [np.busday_count(val_date.date(), e.date()) / TRADING_DAYS for e in df["expiry"]]
    cols = ["expiry", "T", "kind", "strike", "bid", "ask", "mid"]
    return df[cols].sort_values(["expiry", "kind", "strike"]).reset_index(drop=True)


def tree_steps(T: float) -> int:
    return max(MIN_TREE_STEPS, round(T * TRADING_DAYS))


def exercise_dates(T: float) -> int:
    return int(min(max(1, round(T * TRADING_DAYS)), MAX_EXERCISE_DATES))


def price_quotes(quotes: pd.DataFrame, S: float, r: float, sigma: float) -> pd.DataFrame:
    """LSM (main), tree (confirmation), Black-Scholes (European) and implied vol per quote."""
    df = quotes.copy()
    lsm = {}
    with progress(desc="LSM Monte Carlo (main)", total=len(df)) as bar:
        for seed, (_, group) in enumerate(df.groupby("expiry")):
            T = group["T"].iloc[0]
            # One path set per expiry, shared by all its strikes.
            dates = exercise_dates(T)
            paths = simulate_paths(S, T, r, sigma, 0.0, dates, LSM_PATHS_PER_EXPIRY, seed)
            for i, K, kind in zip(group.index, group["strike"], group["kind"]):
                lsm[i] = lsm_on_paths(paths, S, K, T, r, sigma, 0.0, kind)
                bar.update()
    df["lsm"] = [lsm[i].price for i in df.index]
    df["lsm_se"] = [lsm[i].stderr for i in df.index]

    contracts = list(zip(df["strike"], df["T"], df["kind"]))
    df["tree_am"] = [
        tree_price(S, K, T, r, sigma, 0.0, tree_steps(T), kind)
        for K, T, kind in progress(contracts, "Binomial tree (confirmation)")
    ]
    df["bs_eu"] = [
        bs_price(S, K, T, r, sigma, 0.0, kind)
        for K, T, kind in progress(contracts, "Black-Scholes (European)")
    ]
    # Implied vol solves on the tree: root-finding needs a smooth price, and LSM is noisy.
    df["iv"] = [
        implied_vol(mid, S, K, T, r, 0.0, tree_steps(T), kind)
        for mid, (K, T, kind) in progress(list(zip(df["mid"], contracts)), "Implied vol (tree)")
    ]
    # Out of the money: calls at or above spot, puts below. These define the smile.
    df["otm"] = np.where(df["kind"] == "call", df["strike"] >= S, df["strike"] < S)
    return df


def surface_fit(smile_quotes: pd.DataFrame, S: float) -> pd.DataFrame:
    """Implied vol on SURFACE_GRID, linear in K / S, for expiries whose quotes span the grid.
    No extrapolation: an expiry that does not cover the grid is left out."""
    columns = {}
    for expiry, group in smile_quotes.groupby("expiry"):
        moneyness = group["strike"].to_numpy() / S  # sorted: smile_quotes is sorted by strike
        if moneyness[0] <= SURFACE_GRID[0] and moneyness[-1] >= SURFACE_GRID[-1]:
            columns[expiry] = np.interp(SURFACE_GRID, moneyness, group["iv"].to_numpy())
    return pd.DataFrame(columns, index=SURFACE_GRID)


def parity_summary(quotes: pd.DataFrame, S: float, r: float) -> pd.DataFrame:
    """Per expiry: call/put pairs on the same strike, and how many satisfy the American bounds
    S - K < C - P < S - K exp(-rT) (Hull, non-dividend American options)."""
    calls = quotes[quotes["kind"] == "call"]
    puts = quotes[quotes["kind"] == "put"]
    pairs = calls.merge(puts, on=["expiry", "strike", "T"], suffixes=("_c", "_p"))
    diff = pairs["mid_c"] - pairs["mid_p"]
    lower = S - pairs["strike"]
    upper = S - pairs["strike"] * np.exp(-r * pairs["T"])
    pairs["ok"] = (diff > lower) & (diff < upper)
    return pairs.groupby("expiry")["ok"].agg(pairs="size", passed="sum").reset_index()


def reference_contract(quotes: pd.DataFrame, S: float) -> tuple[float, float]:
    """(K, T): the strike nearest spot and the expiry nearest one month."""
    K = min(quotes["strike"].unique(), key=lambda k: abs(k - S))
    T = min(quotes["T"].unique(), key=lambda t: abs(t - 21 / TRADING_DAYS))
    return float(K), float(T)


def convergence(S, K, T, r, sigma) -> pd.DataFrame:
    steps = CONVERGENCE_STEPS
    table = pd.DataFrame({"n": steps})
    table["tree_am_put"] = [
        tree_price(S, K, T, r, sigma, 0.0, n, "put") for n in progress(steps, "Tree convergence")
    ]
    table["tree_eu_call"] = [tree_price(S, K, T, r, sigma, 0.0, n, american=False) for n in steps]
    table["bs_call"] = bs_price(S, K, T, r, sigma, 0.0, "call")
    return table


def monte_carlo(S, K, T, r, sigma, exercise_dates: int):
    """LSM put price as the number of paths grows, and a few paths to plot."""
    rows = []
    for n in progress(LSM_PATHS, "LSM convergence in paths"):
        result = lsm_price(S, K, T, r, sigma, 0.0, exercise_dates, n, "put")
        rows.append((n, result.price, result.stderr))
    lsm = pd.DataFrame(rows, columns=["paths", "price", "stderr"])
    shown = simulate_paths(S, T, r, sigma, 0.0, exercise_dates, SHOWN_PATHS, seed=1)
    times = np.linspace(0.0, T, exercise_dates + 1)
    paths = pd.DataFrame(np.column_stack([np.full(SHOWN_PATHS, S), shown]).T, index=times)
    paths.columns = range(1, SHOWN_PATHS + 1)
    return lsm, paths


def main(name: str | None = None) -> None:
    stage("Loading frozen snapshot")
    snap = load_snapshot(name)
    close = snap["underlying"]
    spot, val_date = float(close.iloc[-1]), close.index[-1]
    rate = float(snap["rate"].iloc[-1]) / 100
    vols = {w: hist_vol(close, n) for w, n in WINDOWS.items()}
    sigma = vols[BASE_WINDOW][0]
    print(f"  Snapshot {snap['meta']['snapshot_date']}: S = {spot:.2f}, r = {rate:.3%}, "
          f"sigma ({BASE_WINDOW}) = {sigma:.2%}")  # fmt: skip

    stage("Cleaning option quotes")
    quotes = clean(snap["chains"], val_date)
    print(f"  {len(quotes)} of {len(snap['chains'])} quotes kept")

    stage("Pricing every quote")
    quotes = price_quotes(quotes, spot, rate, sigma)
    smile_quotes = quotes[quotes["otm"] & quotes["iv"].notna()].sort_values(["expiry", "strike"])

    stage("Fitting the volatility surface and checking put-call bounds")
    fit = surface_fit(smile_quotes, spot)
    parity = parity_summary(quotes, spot, rate)

    K, T = reference_contract(quotes, spot)
    stage(f"Studying the ATM put (K = {K:g}, T = {T:.3f} years)")
    dates = exercise_dates(T)
    conv = convergence(spot, K, T, rate, sigma)
    lsm, sample_paths = monte_carlo(spot, K, T, rate, sigma, dates)
    benchmarks = [
        (f"Binomial tree, American ({BENCHMARK_STEPS} time steps)",
         tree_price(spot, K, T, rate, sigma, 0.0, BENCHMARK_STEPS, "put")),
        ("Black-Scholes, European", bs_price(spot, K, T, rate, sigma, 0.0, "put")),
    ]  # fmt: skip

    stage("Running model validation (dummy data and textbook values)")
    validation = validation_sections()

    run = PricingRun(
        snapshot=snap["meta"]["snapshot_date"],
        pulled_utc=pd.Timestamp(snap["meta"]["pulled_utc"]),
        val_date=val_date,
        spot=spot,
        rate=rate,
        vols=vols,
        window_days=WINDOWS,
        base_window=BASE_WINDOW,
        n_steps=MIN_TREE_STEPS,
        max_spread=MAX_SPREAD,
        n_pulled=len(snap["chains"]),
        quotes=quotes,
        smile_quotes=smile_quotes,
        surface_fit=fit,
        parity=parity,
        validation=validation,
        dividend_lattice=dividend_call_lattice(),
        contract=f"ATM put: K = {K:g}, T = {T:.3f} years, σ = {sigma:.2%}",
        strike=K,
        lattice=tree_lattice(spot, K, T, rate, sigma, 0.0, LATTICE_STEPS, "put"),
        convergence=conv,
        benchmarks=benchmarks,
        lsm=lsm,
        exercise_dates=dates,
        lsm_paths=LSM_PATHS_PER_EXPIRY,
        max_exercise_dates=MAX_EXERCISE_DATES,
        confirm_tolerance=CONFIRM_TOLERANCE,
        sample_paths=sample_paths,
    )

    stage("Writing the Excel workbook")
    out = ROOT / "reports" / f"{run.snapshot}_pricing.xlsx"
    out.parent.mkdir(exist_ok=True)
    write_report(out, run)
    confirmed = (
        (quotes["lsm"] - quotes["tree_am"]).abs() <= 2 * quotes["lsm_se"] + CONFIRM_TOLERANCE
    ).mean()
    print(f"  Tree confirms LSM on {confirmed:.1%} of quotes")
    print(f"\nDone. Wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
