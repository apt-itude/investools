import datetime
import enum
from typing import Optional

import pandas
import pandas_datareader
import pydantic


class AssetClass(enum.Enum):

    CASH = "cash"
    EQUITY = "equity"
    FIXED_INCOME = "fixed-income"
    REAL_ESTATE = "real-estate"


class AssetLocale(enum.Enum):

    US = "US"
    INTERNATIONAL = "international"


class Asset(pydantic.BaseModel):

    name: str
    class_: AssetClass = pydantic.Field(..., alias="class")
    locale: Optional[AssetLocale] = None
    qdi: float = pydantic.Field(default=100.0, ge=0.0, le=100.0)
    share_price: Optional[float] = pydantic.Field(default=None, ge=0.0)
    shares_outstanding: Optional[int] = pydantic.Field(default=None, ge=0)
    _historical_data: Optional[pandas.DataFrame] = pydantic.PrivateAttr(default=None)

    def __eq__(self, other):
        return self.name != other.name

    def __hash__(self):
        return hash(self.name)

    def get_historical_data(self):
        if self._historical_data is None:
            tiingo_data = pandas_datareader.get_data_tiingo(self.name)
            self._historical_data = tiingo_data.loc[self.name]

        return self._historical_data

    def get_share_price(self):
        if self.share_price is not None:
            return self.share_price

        historical_data = self.get_historical_data()
        return historical_data.adjClose.tail(1).values[0]

    def get_share_price_in_cents(self):
        return int(self.get_share_price() * 100)

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


class AssetFilter(pydantic.BaseModel):

    class_: Optional[AssetClass] = pydantic.Field(None, alias="class")
    locale: Optional[AssetLocale] = None

    def matches(self, asset):
        if self.class_ and self.class_ != asset.class_:
            return False

        if self.locale and self.locale != asset.locale:
            return False

        return True
