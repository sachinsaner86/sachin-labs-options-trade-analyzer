"""Black-Scholes pricing and Greeks calculation.

Extracted from options_pl_tracker.py for reuse. Deferred from dashboard v1
but extracted now for clean separation.
"""

import numpy as np
from scipy.stats import norm


def black_scholes_call(S, K, T, r, sigma):
    """Calculate Black-Scholes call option price."""
    if T <= 0:
        return max(S - K, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


def black_scholes_put(S, K, T, r, sigma):
    """Calculate Black-Scholes put option price."""
    if T <= 0:
        return max(K - S, 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def option_greeks(S, K, T, r, sigma, option_type='call'):
    """Calculate option Greeks."""
    if T <= 0:
        intrinsic = max(S - K, 0) if option_type == 'call' else max(K - S, 0)
        return {
            'delta': (1.0 if S > K else 0.0) if option_type == 'call' else (-1.0 if S < K else 0.0),
            'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'price': intrinsic
        }

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100

    if option_type == 'call':
        price = black_scholes_call(S, K, T, r, sigma)
        delta = norm.cdf(d1)
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        price = black_scholes_put(S, K, T, r, sigma)
        delta = norm.cdf(d1) - 1
        theta = (-(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365

    return {'delta': delta, 'gamma': gamma, 'theta': theta, 'vega': vega, 'price': price}


def calculate_position_pl(legs, spot_prices, dte_values, r=0.045):
    """Calculate P/L grid for a multi-leg options position."""
    pl_grid = np.zeros((len(dte_values), len(spot_prices)))
    total_entry_cost = sum(leg['entry_price'] * leg['qty'] * 100 for leg in legs)

    for i, dte in enumerate(dte_values):
        T = max(dte / 365.0, 0.0)
        for j, S in enumerate(spot_prices):
            position_value = 0
            for leg in legs:
                if leg['type'] == 'call':
                    price = black_scholes_call(S, leg['strike'], T, r, leg['iv'])
                else:
                    price = black_scholes_put(S, leg['strike'], T, r, leg['iv'])
                position_value += price * leg['qty'] * 100
            pl_grid[i, j] = position_value - total_entry_cost

    return pl_grid, total_entry_cost


def calculate_greeks_profile(legs, spot_price, dte, r=0.045):
    """Calculate net Greeks for a position at a given spot and DTE."""
    T = max(dte / 365.0, 0.001)
    net_greeks = {'delta': 0, 'gamma': 0, 'theta': 0, 'vega': 0}

    for leg in legs:
        greeks = option_greeks(spot_price, leg['strike'], T, r, leg['iv'], leg['type'])
        for g in net_greeks:
            net_greeks[g] += greeks[g] * leg['qty'] * 100

    return net_greeks
