import typing as t
import warnings

import pandas

from investools import history, model


def project_tax_exempt_rates(
    assets: t.Iterable[model.Asset],
    total_market_asset_ticker: str = "ACWI",
) -> t.Dict[str, float]:

    market_history = history.AssetHistory.from_tiingo(total_market_asset_ticker)
    market_prices = market_history.data.adjClose
    risk_aversion = _get_market_implied_risk_aversion(market_prices)

    market_caps_by_asset = {
        asset.ticker: asset.get_market_capitalization() for asset in assets
    }
    annual_returns_by_asset = {
        asset.ticker: history.AssetHistory.from_tiingo(
            asset.ticker
        ).get_annual_returns()
        for asset in assets
    }
    covariance_matrix = pandas.DataFrame(annual_returns_by_asset).cov()

    return _get_market_implied_prior_returns(
        market_caps_by_asset, risk_aversion, covariance_matrix
    )


def project_tax_deferred_rate(
    asset: model.Asset,
    tax_exempt_return_rate: float,
    years: int,
    ordinary_tax_rate: float,
) -> float:
    """
    Reference: https://www.betterment.com/resources/asset-location-methodology/#part-4
    See "Deriving Account-Specific After-Tax Return" #2
    """
    current_value = asset.share_price
    return _get_annualized_post_tax_return_rate(
        current_value, tax_exempt_return_rate, years, ordinary_tax_rate
    )


def project_taxable_rate(
    asset: model.Asset,
    tax_exempt_return_rate: float,
    years: int,
    ordinary_tax_rate: float,
    preferential_tax_rate: float,
) -> float:
    """
    Reference: https://www.betterment.com/resources/asset-location-methodology/#part-4
    See "Deriving Account-Specific After-Tax Return" #3
    """
    asset_history = history.AssetHistory.from_tiingo(asset.ticker)
    average_annual_dividend = asset_history.get_annual_dividends().mean()

    qualified_dividends = average_annual_dividend * asset.qdi
    unqualified_dividends = average_annual_dividend - qualified_dividends
    dividend_taxes = (
        qualified_dividends * preferential_tax_rate
        + unqualified_dividends * ordinary_tax_rate
    )

    current_value = asset.share_price
    annual_return = current_value * tax_exempt_return_rate
    # The tax-exempt return rate is calcuated using "adjusted close" prices, which
    # factor in dividends, so this rate includes growth resulting from dividends
    post_tax_annual_return = annual_return - dividend_taxes
    adjusted_annual_return_rate = post_tax_annual_return / current_value

    return _get_annualized_post_tax_return_rate(
        current_value,
        adjusted_annual_return_rate,
        years,
        preferential_tax_rate,
    )


def _get_annualized_post_tax_return_rate(
    current_value: float,
    return_rate: float,
    years: int,
    tax_rate: float,
) -> float:
    projected_pre_tax_value = current_value * (1 + return_rate) ** years
    growth = projected_pre_tax_value - current_value
    taxes = growth * tax_rate
    projected_post_tax_value = projected_pre_tax_value - taxes
    return (projected_post_tax_value / current_value) ** (1 / years) - 1


# Both functions below completely jacked from here:
# https://github.com/robertmartin8/PyPortfolioOpt/blob/master/pypfopt/black_litterman.py


def _get_market_implied_risk_aversion(
    market_prices: t.Union[pandas.Series, pandas.DataFrame],
    frequency: int = 252,
    risk_free_rate: float = 0.02,
) -> float:
    r"""
    Calculate the market-implied risk-aversion parameter (i.e market price of risk)
    based on market prices. For example, if the market has excess returns of 10% a year
    with 5% variance, the risk-aversion parameter is 2, i.e you have to be compensated 2x
    the variance.
    .. math::
        \delta = \frac{R - R_f}{\sigma^2}
    :param market_prices: the (daily) prices of the market portfolio, e.g SPY.
    :type market_prices: pandas.Series with DatetimeIndex.
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
    rets = market_prices.pct_change().dropna()
    rate = float(rets.mean() * frequency)
    var = float(rets.var() * frequency)
    return (rate - risk_free_rate) / var


def _get_market_implied_prior_returns(
    market_caps: t.Mapping[str, float],
    risk_aversion: float,
    cov_matrix: pandas.DataFrame,
    risk_free_rate: float = 0.02,
) -> t.Dict[str, float]:
    r"""
    Compute the prior estimate of returns implied by the market weights.
    In other words, given each asset's contribution to the risk of the market
    portfolio, how much are we expecting to be compensated?
    .. math::
        \Pi = \delta \Sigma w_{mkt}
    :param market_caps: market capitalisations of all assets
    :type market_caps: {ticker: cap} dict or pandas.Series
    :param risk_aversion: risk aversion parameter
    :type risk_aversion: positive float
    :param cov_matrix: covariance matrix of asset returns
    :type cov_matrix: pandas.DataFrame
    :param risk_free_rate: risk-free rate of borrowing/lending, defaults to 0.02.
                           You should use the appropriate time period, corresponding
                           to the covariance matrix.
    :type risk_free_rate: float, optional
    :return: prior estimate of returns as implied by the market caps
    :rtype: dict
    """
    if not isinstance(cov_matrix, pandas.DataFrame):
        warnings.warn(
            "If cov_matrix is not a dataframe, market cap index must be aligned to cov_matrix",
            RuntimeWarning,
        )
    mcaps = pandas.Series(market_caps)
    mkt_weights = mcaps / mcaps.sum()
    # Pi is excess returns so must add risk_free_rate to get return.
    returns_as_series = risk_aversion * cov_matrix.dot(mkt_weights) + risk_free_rate
    return dict(returns_as_series)
