"""Longstaff-Schwartz least-squares Monte Carlo for American options under Black-Scholes GBM.

At each exercise date, in-the-money paths regress their discounted future cash flow on
(1, x, x^2, x^3) with x = S / K. A path exercises when the payoff beats the fitted
continuation value.
"""

import numpy as np

MIN_REGRESSION_PATHS = 4  # a cubic fit needs more points than coefficients


def simulate_paths(S, T, r, sigma, q=0.0, n_steps=50, n_paths=100_000, seed=0):
    """Risk-neutral GBM paths at times dt, 2dt, ..., T. Shape (n_paths, n_steps)."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    shocks = rng.standard_normal((n_paths, n_steps))
    log_steps = (r - q - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
    return S * np.exp(np.cumsum(log_steps, axis=1))


def lsm_price(S, K, T, r, sigma, q=0.0, n_steps=50, n_paths=100_000, kind="put", seed=0):
    """Return (price, standard error)."""
    paths = simulate_paths(S, T, r, sigma, q, n_steps, n_paths, seed)
    sign = 1.0 if kind == "call" else -1.0
    disc = np.exp(-r * T / n_steps)

    cash = np.maximum(sign * (paths[:, -1] - K), 0.0)  # value at expiry
    for t in range(n_steps - 2, -1, -1):
        cash *= disc  # now valued at exercise date t
        exercise = np.maximum(sign * (paths[:, t] - K), 0.0)
        itm = exercise > 0
        if itm.sum() > MIN_REGRESSION_PATHS:
            x = paths[itm, t] / K
            continuation = np.polyval(np.polyfit(x, cash[itm], 3), x)
            exercise_now = np.flatnonzero(itm)[exercise[itm] > continuation]
            cash[exercise_now] = exercise[exercise_now]
    cash *= disc  # from the first exercise date back to today

    price = max(cash.mean(), max(sign * (S - K), 0.0))  # or exercise immediately
    return float(price), float(cash.std(ddof=1) / np.sqrt(n_paths))
