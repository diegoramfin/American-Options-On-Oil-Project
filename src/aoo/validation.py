"""Model validation on dummy data and textbook values, independent of market data.

Single source for the tests and the Validation sheet of the Excel report. Each section is
(title, rows of (label, reference, model), note).
"""

import numpy as np

from aoo.bs import bs_price
from aoo.lsm import lsm_price
from aoo.tree import tree_lattice, tree_price

# Dummy data. q = 0 unless stated.
DUMMY = {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20}
DUMMY_BS_PRICES = {"call": 10.4506, "put": 5.5735}  # standard four-decimal benchmark
DUMMY_DIVIDEND = 0.08  # large enough that early exercise of the call clearly pays
DUMMY_TREE_STEPS = 1000
DUMMY_LATTICE_STEPS = 6

# Hull, Options, Futures and Other Derivatives.
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
        (f"American put, {n}-step tree", ref, tree_price(**HULL_PUT, n=n, kind="put"))
        for n, ref in HULL_PUT_BY_STEPS.items()
    ]
    bs = [
        (f"European {kind}, Black-Scholes", ref, bs_price(**HULL_BS, kind=kind))
        for kind, ref in HULL_BS_PRICES.items()
    ]
    return tree + bs


def dividend_call_lsm():
    return lsm_price(**DUMMY, q=DUMMY_DIVIDEND, n_steps=50, kind="call")


def dividend_call_lattice():
    """Small lattice of the dividend call, to show where early exercise is optimal."""
    return tree_lattice(**DUMMY, q=DUMMY_DIVIDEND, n=DUMMY_LATTICE_STEPS, kind="call")


def validation_sections() -> list[tuple[str, list[tuple[str, float, float]], str]]:
    n = DUMMY_TREE_STEPS
    bs = {kind: bs_price(**DUMMY, kind=kind) for kind in ("call", "put")}
    tree = {
        (kind, american): tree_price(**DUMMY, n=n, kind=kind, american=american)
        for kind in ("call", "put")
        for american in (True, False)
    }
    parity = DUMMY["S"] - DUMMY["K"] * np.exp(-DUMMY["r"] * DUMMY["T"])

    q = DUMMY_DIVIDEND
    bs_q = bs_price(**DUMMY, q=q, kind="call")
    tree_q = tree_price(**DUMMY, q=q, n=n, kind="call")
    lsm_q = dividend_call_lsm()

    inputs = "S = K = 100, T = 1, r = 5%, σ = 20%"
    return [
        (
            f"Dummy data: Black-Scholes ({inputs})",
            [
                ("European call", DUMMY_BS_PRICES["call"], bs["call"]),
                ("European put", DUMMY_BS_PRICES["put"], bs["put"]),
                ("Put-call parity: C − P vs S − K·e^(−rT)", parity, bs["call"] - bs["put"]),
            ],
            "References are the standard four-decimal benchmark values.",
        ),
        (
            f"Dummy data: binomial tree with {n:,} time steps (same inputs)",
            [
                ("European call: tree vs Black-Scholes", bs["call"], tree["call", False]),
                ("European put: tree vs Black-Scholes", bs["put"], tree["put", False]),
                ("American call vs European call (no dividend)", bs["call"], tree["call", True]),
                ("American put vs European put", bs["put"], tree["put", True]),
            ],
            "With no dividend the American call equals the European call. For the put, the "
            "difference is the early-exercise premium.",
        ),
        (
            "Textbook values (Hull)",
            reference_checks(),
            "Hull, Options, Futures and Other Derivatives: American put S = K = 50, r = 10%, "
            "σ = 40%, T = 5 months; Black-Scholes S = 42, K = 40, r = 10%, σ = 20%, T = 6 months.",
        ),
        (
            f"Dummy data: American call with {q:.0%} dividend yield (same inputs)",
            [
                ("American call (tree) vs European call (Black-Scholes)", bs_q, tree_q),
                ("American call: LSM vs tree", tree_q, lsm_q.price),
            ],
            f"The first difference is the early-exercise premium. LSM: {lsm_q.stderr:.4f} "
            f"standard error, {lsm_q.early_exercise:.1%} of paths exercised before expiry. "
            "The lattice below shades the nodes where exercising now beats holding.",
        ),
    ]
