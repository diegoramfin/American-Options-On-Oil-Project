"""Longstaff-Schwartz least-squares Monte Carlo (LSM) for American options.

Assumptions: the Black-Scholes model. Paths follow risk-neutral GBM, simulated exactly:
    S(t + dt) = S(t) exp((r - q - sigma^2 / 2) dt + sigma sqrt(dt) Z),   Z ~ N(0, 1)
Exercise is allowed on n_steps equally spaced dates (dt = T / n_steps), so the price is a
Bermudan approximation of the American price that improves as n_steps grows.

Backward induction (Longstaff and Schwartz, 2001), from the last exercise date to the first:
    - In-the-money paths regress their realised discounted future cash flow on the basis
      (1, x, x^2, x^3) with x = S / K. The fitted value is the continuation value C.
    - A path exercises when the payoff now exceeds C; its later cash flows are dropped.
    - The price is the mean of all cash flows discounted to today.
The exercise policy is estimated, so LSM is slightly low-biased. With q = 0 a call is never
exercised early, so calls skip the regression.

Black-Scholes control variate: on the same paths, the discounted European payoff Y has a
known mean, the Black-Scholes price. With X the discounted LSM cash flow per path,
    price = mean(X - beta (Y - BS)),   beta = cov(X, Y) / var(Y),
which roughly halves the standard error at no extra simulation cost.
"""

from typing import NamedTuple

import numpy as np

from aoo.bs import bs_price

MIN_REGRESSION_PATHS = 4  # a cubic fit needs more points than coefficients


class LsmResult(NamedTuple):
    price: float
    stderr: float
    early_exercise: float  # share of paths exercised before expiry


def simulate_paths(S, T, r, sigma, q=0.0, n_steps=50, n_paths=100_000, seed=0):
    """Risk-neutral GBM paths at times dt, 2dt, ..., T. Shape (n_paths, n_steps)."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    shocks = rng.standard_normal((n_paths, n_steps))
    log_steps = (r - q - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
    return S * np.exp(np.cumsum(log_steps, axis=1))


def lsm_price(
    S, K, T, r, sigma, q=0.0, n_steps=50, n_paths=100_000, kind="put", seed=0
) -> LsmResult:
    """Simulate n_paths paths with n_steps exercise dates and price on them."""
    paths = simulate_paths(S, T, r, sigma, q, n_steps, n_paths, seed)
    return lsm_on_paths(paths, S, K, T, r, sigma, q, kind)


def lsm_on_paths(paths, S, K, T, r, sigma, q=0.0, kind="put") -> LsmResult:
    """Price on pre-simulated paths, so all strikes of one expiry can share them."""
    n_paths, n_steps = paths.shape
    sign = 1.0 if kind == "call" else -1.0
    disc = np.exp(-r * T / n_steps)

    # Early exercise of a call is never optimal without a dividend yield. Skipping it avoids
    # spurious exercise when the regression underestimates continuation deep in the money.
    early_exercise = kind == "put" or q > 0

    cash = np.maximum(sign * (paths[:, -1] - K), 0.0)  # value at expiry
    european = np.exp(-r * T) * cash  # control: discounted European payoff
    exercised_early = np.zeros(n_paths, dtype=bool)
    for t in range(n_steps - 2, -1, -1):
        cash *= disc  # now valued at exercise date t
        exercise = np.maximum(sign * (paths[:, t] - K), 0.0)
        itm = exercise > 0
        if early_exercise and itm.sum() > MIN_REGRESSION_PATHS:
            x = paths[itm, t] / K
            continuation = np.polyval(np.polyfit(x, cash[itm], 3), x)
            exercise_now = np.flatnonzero(itm)[exercise[itm] > continuation]
            cash[exercise_now] = exercise[exercise_now]
            exercised_early[exercise_now] = True
    cash *= disc  # from the first exercise date back to today

    control_var = european.var(ddof=1)
    beta = np.cov(cash, european)[0, 1] / control_var if control_var > 0 else 0.0
    adjusted = cash - beta * (european - bs_price(S, K, T, r, sigma, q, kind))
    price = max(adjusted.mean(), max(sign * (S - K), 0.0))  # or exercise immediately
    stderr = adjusted.std(ddof=1) / np.sqrt(n_paths)
    return LsmResult(float(price), float(stderr), float(exercised_early.mean()))
