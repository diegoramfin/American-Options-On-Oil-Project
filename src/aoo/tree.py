"""Cox-Ross-Rubinstein (CRR) binomial tree for European and American options.

Assumptions: the Black-Scholes model (GBM with constant r, q, sigma), discretised in time.
The option's life T is split into n time steps of length dt = T / n; each step the price
moves up by u or down by d:
    u = e^(sigma sqrt(dt)),   d = 1 / u,   p = (e^((r - q) dt) - d) / (u - d)
where p is the risk-neutral probability of an up move. After i steps with j up moves the
price is S u^(2j - i).

Backward induction from the payoff at expiry:
    hold = e^(-r dt) [p V(up) + (1 - p) V(down)]
    European: V = hold;   American: V = max(hold, payoff from exercising now)

The price converges to the Black-Scholes model value as n grows; the error oscillates in n
and shrinks roughly like 1 / n. Implied vol is the sigma at which the American tree price
equals a market price, found with Brent's root-finder.
"""

import numpy as np
from scipy.optimize import brentq

IV_BOUNDS = (1e-3, 3.0)  # implied-vol search range: 0.1% to 300%


def tree_price(S, K, T, r, sigma, q=0.0, n=100, kind="call", american=True):
    """Option price from an n-time-step tree. kind is "call" or "put"."""
    return _backward_induction(S, K, T, r, sigma, q, n, kind, american)[0]


def tree_lattice(S, K, T, r, sigma, q=0.0, n=5, kind="put", american=True):
    """For display. Per step i = 0..n: (stock prices, option values, early-exercise flags),
    each indexed by j = number of up-moves."""
    return _backward_induction(S, K, T, r, sigma, q, n, kind, american, record=True)[1]


def implied_vol(price, S, K, T, r, q=0.0, n=100, kind="call"):
    """Sigma at which the American tree matches price. NaN if price <= intrinsic or no root."""
    intrinsic = max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    if price <= intrinsic:
        return np.nan
    try:
        return brentq(lambda s: tree_price(S, K, T, r, s, q, n, kind) - price, *IV_BOUNDS)
    except ValueError:
        return np.nan


def _backward_induction(S, K, T, r, sigma, q, n, kind, american, record=False):
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    disc = np.exp(-r * dt)
    sign = 1.0 if kind == "call" else -1.0

    def stock(i):  # node (i, j): j up-moves out of i steps
        return S * u ** (2 * np.arange(i + 1) - i)

    def payoff(i):
        return np.maximum(sign * (stock(i) - K), 0.0)

    V = payoff(n)
    layers = [(stock(n), V, np.zeros(n + 1, dtype=bool))] if record else []
    for i in range(n - 1, -1, -1):
        V = disc * (p * V[1:] + (1 - p) * V[:-1])
        exercised = np.zeros(i + 1, dtype=bool)
        if american:
            exercised = payoff(i) > V
            V = np.where(exercised, payoff(i), V)
        if record:
            layers.append((stock(i), V, exercised))
    return float(V[0]), layers[::-1]
