"""Correctness checks for the pricers and the volatility estimator. All offline."""

import numpy as np
import pandas as pd
import pytest

from aoo.bs import bs_price
from aoo.lsm import lsm_price
from aoo.tree import implied_vol, tree_lattice, tree_price
from aoo.validation import (
    DUMMY,
    DUMMY_BS_PRICES,
    DUMMY_DIVIDEND,
    HULL_PUT,
    HULL_TOLERANCE,
    dividend_call_lattice,
    dividend_call_lsm,
    reference_checks,
)
from aoo.vol import hist_vol


@pytest.mark.parametrize("kind", ["call", "put"])
def test_bs_dummy_benchmark(kind):
    assert bs_price(**DUMMY, kind=kind) == pytest.approx(DUMMY_BS_PRICES[kind], abs=1e-4)


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
    price, stderr, early = lsm_price(**HULL_PUT, n_steps=50, kind="put")
    assert price == pytest.approx(tree_price(**HULL_PUT, n=500, kind="put"), abs=3 * stderr + 0.01)
    assert early > 0  # some paths exercise the put early


def test_lsm_call_equals_bs_without_dividend():
    # No early exercise for a call when q = 0, so the control variate makes LSM exact.
    price, stderr, early = lsm_price(**HULL_PUT, n_steps=50, kind="call")
    assert price == pytest.approx(bs_price(**HULL_PUT, kind="call"), abs=1e-9)
    assert stderr == pytest.approx(0.0, abs=1e-9)
    assert early == 0.0


def test_dividend_call_exercises_early():
    # With a dividend yield, holding a deep in-the-money call forgoes dividends, so early
    # exercise pays: the American call is worth more than the European call.
    american = tree_price(**DUMMY, q=DUMMY_DIVIDEND, n=1000, kind="call")
    european = bs_price(**DUMMY, q=DUMMY_DIVIDEND, kind="call")
    assert american > european + 0.3
    lsm = dividend_call_lsm()
    assert lsm.price == pytest.approx(american, abs=3 * lsm.stderr + 0.01)
    assert lsm.early_exercise > 0
    # In the lattice, exercise happens only in the money, at the high stock prices.
    for stock, _, exercised in dividend_call_lattice():
        assert (stock[exercised] > DUMMY["K"]).all()
    assert any(exercised.any() for _, _, exercised in dividend_call_lattice())


def test_hist_vol_recovers_known_sigma():
    returns = np.tile([0.01, -0.01], 50)  # 100 returns, stdev (n - 1) = 0.01 * sqrt(100/99)
    close = pd.Series(100 * np.exp(np.concatenate([[0.0], np.cumsum(returns)])))
    sigma, err = hist_vol(close, 100)
    assert sigma == pytest.approx(np.sqrt(252) * 0.01 * np.sqrt(100 / 99), rel=1e-10)
    assert err == pytest.approx(sigma / np.sqrt(200), rel=1e-12)
