"""
Gamma Exposure (GEX) calculation from a free, delayed options chain
(via yfinance / Yahoo Finance). No paid data feed required.

This intentionally reimplements the math from scratch (Black-Scholes gamma)
rather than calling a paid GEX API, so it's fully free and so anyone
following along can see exactly how the numbers are derived.

Standard convention used here (the same one most free/retail GEX tools use):
  - Dealers are assumed net SHORT calls and net LONG puts relative to customers.
  - Call open interest contributes POSITIVE gamma exposure.
  - Put open interest contributes NEGATIVE gamma exposure.
This is a simplification (real dealer positioning isn't public), but it's the
standard proxy used across the retail GEX-tool space, so results are
comparable to what people see elsewhere.
"""

import math
from datetime import datetime, timezone

import numpy as np
import yfinance as yf

CONTRACT_MULTIPLIER = 100  # standard US equity/index option contract size


def _norm_pdf(x):
    return (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x)


def bs_gamma(spot, strike, t_years, iv, r):
    """Black-Scholes gamma for a single option."""
    if t_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / (
        iv * math.sqrt(t_years)
    )
    return _norm_pdf(d1) / (spot * iv * math.sqrt(t_years))


def _years_to_expiry(expiry_str):
    expiry = datetime.strptime(expiry_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max((expiry - now).total_seconds() / (365.0 * 24 * 3600), 0.0)


def fetch_spot(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    fast = ticker.fast_info
    return float(fast["last_price"])


def compute_gex(ticker_symbol, risk_free_rate=0.05, num_expirations=1):
    """
    Returns a dict:
      {
        "spot": float,
        "total_gex": float,
        "gamma_flip": float or None,
        "call_wall": float or None,
        "put_wall": float or None,
        "per_strike": { strike: net_gex, ... }
      }
    """
    ticker = yf.Ticker(ticker_symbol)
    spot = fetch_spot(ticker_symbol)

    expirations = ticker.options[:num_expirations]
    per_strike = {}

    for expiry_str in expirations:
        t_years = _years_to_expiry(expiry_str)
        chain = ticker.option_chain(expiry_str)

        for _, row in chain.calls.iterrows():
            iv = row.get("impliedVolatility", 0.0) or 0.0
            oi = row.get("openInterest", 0.0) or 0.0
            strike = float(row["strike"])
            gamma = bs_gamma(spot, strike, t_years, iv, risk_free_rate)
            gex = gamma * oi * CONTRACT_MULTIPLIER * spot * spot * 0.01
            per_strike[strike] = per_strike.get(strike, 0.0) + gex

        for _, row in chain.puts.iterrows():
            iv = row.get("impliedVolatility", 0.0) or 0.0
            oi = row.get("openInterest", 0.0) or 0.0
            strike = float(row["strike"])
            gamma = bs_gamma(spot, strike, t_years, iv, risk_free_rate)
            gex = -gamma * oi * CONTRACT_MULTIPLIER * spot * spot * 0.01
            per_strike[strike] = per_strike.get(strike, 0.0) + gex

    if not per_strike:
        return {
            "spot": spot,
            "total_gex": 0.0,
            "gamma_flip": None,
            "call_wall": None,
            "put_wall": None,
            "per_strike": {},
        }

    strikes_sorted = sorted(per_strike.keys())
    total_gex = sum(per_strike.values())

    # Gamma flip: strike where cumulative GEX (ascending strikes) crosses zero
    cumulative = 0.0
    gamma_flip = None
    prev_strike, prev_cum = None, None
    for strike in strikes_sorted:
        cumulative += per_strike[strike]
        if prev_cum is not None and (prev_cum < 0) != (cumulative < 0):
            # crossed zero between prev_strike and strike -> linear interpolate
            span = cumulative - prev_cum
            gamma_flip = strike if span == 0 else (
                prev_strike + (strike - prev_strike) * (-prev_cum / span)
            )
            break
        prev_strike, prev_cum = strike, cumulative

    call_wall = max(per_strike, key=per_strike.get)
    put_wall = min(per_strike, key=per_strike.get)

    return {
        "spot": spot,
        "total_gex": total_gex,
        "gamma_flip": gamma_flip,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "per_strike": per_strike,
    }
