"""Textbook reference values from Hull, Options, Futures and Other Derivatives.

Single source for the tests and the Checks sheet of the Excel report.
"""

from aoo.bs import bs_price
from aoo.tree import tree_price

# Binomial-tree example: American put, S = K = 50, r = 10%, sigma = 40%, T = 5 months.
HULL_PUT = {"S": 50.0, "K": 50.0, "T": 5 / 12, "r": 0.10, "sigma": 0.40}
HULL_PUT_BY_STEPS = {5: 4.49, 30: 4.263, 50: 4.272, 100: 4.278, 500: 4.283}

# Black-Scholes example: S = 42, K = 40, r = 10%, sigma = 20%, T = 6 months.
HULL_BS = {"S": 42.0, "K": 40.0, "T": 0.5, "r": 0.10, "sigma": 0.20}
HULL_BS_PRICES = {"call": 4.76, "put": 0.81}

HULL_TOLERANCE = 0.005  # Hull prints these to two or three decimals


def reference_checks() -> list[tuple[str, float, float]]:
    """(label, value printed in Hull, value from our model)."""
    tree = [
        (f"American put, tree n={n}", ref, tree_price(**HULL_PUT, n=n, kind="put"))
        for n, ref in HULL_PUT_BY_STEPS.items()
    ]
    bs = [
        (f"European {kind}, Black-Scholes", ref, bs_price(**HULL_BS, kind=kind))
        for kind, ref in HULL_BS_PRICES.items()
    ]
    return tree + bs
