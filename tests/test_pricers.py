"""Correctness checks for the pricers and the volatility estimator. All offline."""

import numpy as np
import pandas as pd
import pytest

from aoo.bs import bs_price
from aoo.lsm import lsm_price
from aoo.tree import implied_vol, tree_lattice, tree_price
from aoo.validation import HULL_PUT, HULL_TOLERANCE, reference_checks
from aoo.vol import hist_vol


def test_bs_standard_benchmark():
    # S = K = 100, T = 1, r = 5%, sigma = 20%: the usual four-decimal benchmark.
    assert bs_price(100, 100, 1, 0.05, 0.2, kind="call") == pytest.approx(10.4506, abs=1e-4)
    assert bs_price(100, 100, 1, 0.05, 0.2, kind="put") == pytest.approx(5.5735, abs=1e-4)


def test_bs_put_call_parity():
    call = bs_price(**HULL_PUT, kind="call")
    put = bs_price(**HULL_PUT, kind="put")
    forward_gap = HULL_PUT["S"] - HULL_PUT["K"] * np.exp(-HULL_PUT["r"] * HULL_PUT["T"])
    assert call - put == pytest.approx(forward_gap, abs=1e-9)


@pytest.mark.parametrize("label, reference, model", reference_checks())
def test_matches_hull(label, reference, model):
    assert model == pytest.approx(reference, abs=HULL_TOLERANCE), label


@pytest.mark.parametrize("kind", ["call", "put"])
def test_tree_european_converges_to_bs(kind):
    # CRR error oscillates in n and shrinks slowly (n=500: 0.003, n=4000: 0.0003).
    tree = tree_price(**HULL_PUT, n=4000, kind=kind, american=False)
    assert tree == pytest.approx(bs_price(**HULL_PUT, kind=kind), abs=0.001)


def test_american_call_equals_european_without_dividend():
    # Early exercise of a call on a non-dividend underlying is never optimal.
    american = tree_price(**HULL_PUT, n=100, kind="call")
    european = tree_price(**HULL_PUT, n=100, kind="call", american=False)
    assert american == pytest.approx(european, abs=1e-6)


@pytest.mark.parametrize("n", [10, 100, 300])
def test_american_put_at_least_european_and_intrinsic(n):
    american = tree_price(**HULL_PUT, n=n, kind="put")
    european = tree_price(**HULL_PUT, n=n, kind="put", american=False)
    assert american >= european - 1e-12
    assert american >= max(HULL_PUT["K"] - HULL_PUT["S"], 0.0) - 1e-12


def test_american_put_deep_itm_exercises_now():
    # Deep in the money with high rates: exercising immediately is optimal.
    american = tree_price(100, 150, 1.0, 0.10, 0.2, n=200, kind="put")
    european = tree_price(100, 150, 1.0, 0.10, 0.2, n=200, kind="put", american=False)
    assert american == pytest.approx(50.0, abs=1e-9)
    assert american > european + 1.0


@pytest.mark.parametrize("kind, K, sigma", [("call", 120, 0.3), ("put", 80, 0.6)])
def test_implied_vol_recovers_sigma(kind, K, sigma):
    price = tree_price(100, K, 0.5, 0.04, sigma, n=100, kind=kind)
    assert implied_vol(price, 100, K, 0.5, 0.04, n=100, kind=kind) == pytest.approx(sigma, abs=1e-6)


def test_implied_vol_is_nan_at_or_below_intrinsic():
    assert np.isnan(implied_vol(10.0, 100, 110, 0.5, 0.04, kind="put"))


def test_lattice_root_matches_tree_price():
    stock, value, exercised = tree_lattice(**HULL_PUT, n=5)[0]
    assert stock[0] == HULL_PUT["S"]
    assert value[0] == pytest.approx(tree_price(**HULL_PUT, n=5, kind="put"), abs=1e-12)


def test_lsm_put_matches_tree():
    # LSM exercises on 50 dates only and is low-biased, so allow 3 standard errors plus 0.01.
    price, stderr = lsm_price(**HULL_PUT, n_steps=50, kind="put")
    assert price == pytest.approx(tree_price(**HULL_PUT, n=500, kind="put"), abs=3 * stderr + 0.01)


def test_lsm_call_matches_bs_without_dividend():
    price, stderr = lsm_price(**HULL_PUT, n_steps=50, kind="call")
    assert price == pytest.approx(bs_price(**HULL_PUT, kind="call"), abs=3 * stderr)


def test_hist_vol_recovers_known_sigma():
    returns = np.tile([0.01, -0.01], 50)  # 100 returns, stdev (n - 1) = 0.01 * sqrt(100/99)
    close = pd.Series(100 * np.exp(np.concatenate([[0.0], np.cumsum(returns)])))
    sigma, err = hist_vol(close, 100)
    assert sigma == pytest.approx(np.sqrt(252) * 0.01 * np.sqrt(100 / 99), rel=1e-10)
    assert err == pytest.approx(sigma / np.sqrt(200), rel=1e-12)
