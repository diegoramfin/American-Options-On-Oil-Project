"""Historical volatility: sigma = sqrt(252) * stdev(daily log returns)."""

import numpy as np
import pandas as pd

TRADING_DAYS = 252
# Lookback windows in trading days: half, a quarter and a twelfth of a trading year.
WINDOWS = {"6m": 126, "3m": 63, "1m": 21}


def hist_vol(close: pd.Series, n_returns: int) -> tuple[float, float]:
    """Return (sigma, standard error) from the last n_returns daily log returns."""
    logret = np.log(close).diff().dropna().iloc[-n_returns:]
    sigma = np.sqrt(TRADING_DAYS) * logret.std(ddof=1)
    err = sigma / np.sqrt(2 * n_returns)  # delta sigma / sigma = 1 / sqrt(2 n)
    return float(sigma), float(err)
