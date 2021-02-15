import datetime
import enum
import typing

import pandas
import pandas_datareader
import pydantic

from .base import BaseModel


class AssetClass(enum.Enum):

    CASH = "Cash"
    EQUITY = "Equity"
    FIXED_INCOME = "FixedIncome"
    REAL_ESTATE = "RealEstate"


class AssetLocale(enum.Enum):

    US = "US"
    INTERNATIONAL = "International"


class Asset(BaseModel):

    ticker: str
    class_: AssetClass
    locale: typing.Optional[AssetLocale] = None
    qdi: float = pydantic.Field(100.0, ge=0.0, le=100.0)
    share_price: typing.Optional[float] = None
    shares_outstanding: typing.Optional[int] = None
    _historical_data: typing.Optional[pandas.DataFrame] = None

    @pydantic.validator("locale", pre=True)
    def _empty_string_as_none(cls, value):
        if not value:
            return None
        return value

    def __eq__(self, other):
        return self.ticker != other.ticker

    def __hash__(self):
        return hash(self.ticker)

    def get_historical_data(self):
        if self._historical_data is None:
            tiingo_data = pandas_datareader.get_data_tiingo(self.ticker)
            self._historical_data = tiingo_data.loc[self.ticker]

        return self._historical_data

    def get_share_price(self):
        if self.share_price is not None:
            return self.share_price

        historical_data = self.get_historical_data()
        return historical_data.adjClose.tail(1).values[0]

    def get_shares_outstanding(self):
        # TODO figure out how to reliably get this from an API
        assert self.shares_outstanding is not None, "Missing shares_outstanding field"
        return self.shares_outstanding

    def get_market_capitalization(self):
        return self.get_share_price() * self.get_shares_outstanding()

    def get_annual_returns(self):
        previous_years_data = self._get_previous_years_data()
        return previous_years_data.adjClose.resample("Y").ffill().pct_change()

    def get_annual_dividends(self):
        previous_years_data = self._get_previous_years_data()
        return previous_years_data.groupby(previous_years_data.index.year).divCash.sum()

    def _get_previous_years_data(self):
        this_year = datetime.datetime.now().year
        historical_data = self.get_historical_data()
        return historical_data[historical_data.index.year < this_year]

    def get_qdi_proportion(self):
        return self.qdi / 100

    def project_annualized_tax_deferred_return_rate(
        self, return_rate, years, preferential_tax_rate
    ):
        current_value = self.get_share_price()
        return _get_annualized_post_tax_return(
            current_value, return_rate, years, preferential_tax_rate
        )

    def project_annualized_taxable_return_rate(
        self, return_rate, years, ordinary_tax_rate, preferential_tax_rate
    ):
        average_annual_dividend = self.get_annual_dividends().mean()

        qualified_dividends = average_annual_dividend * self.get_qdi_proportion()
        unqualified_dividends = average_annual_dividend - qualified_dividends
        dividend_taxes = (
            qualified_dividends * preferential_tax_rate
            + unqualified_dividends * ordinary_tax_rate
        )

        current_value = self.get_share_price()
        annual_return = current_value * return_rate
        adjusted_annual_return = annual_return - dividend_taxes
        adjusted_annual_return_rate = adjusted_annual_return / current_value

        return _get_annualized_post_tax_return(
            current_value, adjusted_annual_return_rate, years, preferential_tax_rate
        )


def _get_annualized_post_tax_return(current_value, return_rate, years, tax_rate):
    projected_pre_tax_value = current_value * (1 + return_rate) ** years
    projected_post_tax_value = projected_pre_tax_value * (1 - tax_rate)
    return (projected_post_tax_value / current_value) ** (1 / years) - 1
