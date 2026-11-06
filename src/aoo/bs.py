"""Black-Scholes-Merton price of a European option (exercise only at expiry).

Assumptions: under the risk-neutral measure the underlying follows geometric Brownian motion,
    dS = (r - q) S dt + sigma S dW,
with constant risk-free rate r, dividend yield q and volatility sigma; frictionless,
continuously traded market. For BNO, q = 0.

Formula (S spot, K strike, T years to expiry, N the standard normal CDF):
    d1 = [ln(S / K) + (r - q + sigma^2 / 2) T] / (sigma sqrt(T)),   d2 = d1 - sigma sqrt(T)
    call = S e^(-qT) N(d1) - K e^(-rT) N(d2)
    put  = K e^(-rT) N(-d2) - S e^(-qT) N(-d1)
"""

import math

from scipy.stats import norm


def bs_price(S, K, T, r, sigma, q=0.0, kind="call"):
    if T <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    if kind == "call":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
