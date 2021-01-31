# Completely jacked from https://github.com/robertmartin8/PyPortfolioOpt/blob/master/pypfopt/black_litterman.py

import warnings

import pandas as pd


def market_implied_prior_returns(
    market_caps, risk_aversion, cov_matrix, risk_free_rate=0.02
):
    r"""
    Compute the prior estimate of returns implied by the market weights.
    In other words, given each asset's contribution to the risk of the market
    portfolio, how much are we expecting to be compensated?
    .. math::
        \Pi = \delta \Sigma w_{mkt}
    :param market_caps: market capitalisations of all assets
    :type market_caps: {ticker: cap} dict or pd.Series
    :param risk_aversion: risk aversion parameter
    :type risk_aversion: positive float
    :param cov_matrix: covariance matrix of asset returns
    :type cov_matrix: pd.DataFrame
    :param risk_free_rate: risk-free rate of borrowing/lending, defaults to 0.02.
                           You should use the appropriate time period, corresponding
                           to the covariance matrix.
    :type risk_free_rate: float, optional
    :return: prior estimate of returns as implied by the market caps
    :rtype: pd.Series
    """
    if not isinstance(cov_matrix, pd.DataFrame):
        warnings.warn(
            "If cov_matrix is not a dataframe, market cap index must be aligned to cov_matrix",
            RuntimeWarning,
        )
    mcaps = pd.Series(market_caps)
    mkt_weights = mcaps / mcaps.sum()
    # Pi is excess returns so must add risk_free_rate to get return.
    return risk_aversion * cov_matrix.dot(mkt_weights) + risk_free_rate


def market_implied_risk_aversion(market_prices, frequency=252, risk_free_rate=0.02):
    r"""
    Calculate the market-implied risk-aversion parameter (i.e market price of risk)
    based on market prices. For example, if the market has excess returns of 10% a year
    with 5% variance, the risk-aversion parameter is 2, i.e you have to be compensated 2x
    the variance.
    .. math::
        \delta = \frac{R - R_f}{\sigma^2}
    :param market_prices: the (daily) prices of the market portfolio, e.g SPY.
    :type market_prices: pd.Series with DatetimeIndex.
    :param frequency: number of time periods in a year, defaults to 252 (the number
                      of trading days in a year)
    :type frequency: int, optional
    :param risk_free_rate: risk-free rate of borrowing/lending, defaults to 0.02.
                            The period of the risk-free rate should correspond to the
                            frequency of expected returns.
    :type risk_free_rate: float, optional
    :raises TypeError: if market_prices cannot be parsed
    :return: market-implied risk aversion
    :rtype: float
    """
    if not isinstance(market_prices, (pd.Series, pd.DataFrame)):
        raise TypeError("Please format market_prices as a pd.Series")
    rets = market_prices.pct_change().dropna()
    r = rets.mean() * frequency
    var = rets.var() * frequency
    return (r - risk_free_rate) / var
