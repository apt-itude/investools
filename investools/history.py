import dataclasses
import datetime

import pandas
import pandas_datareader


@dataclasses.dataclass
class AssetHistory:

    _historical_data: pandas.DataFrame

    @classmethod
    def from_tiingo(cls, ticker):
        tiingo_data = pandas_datareader.get_data_tiingo(ticker)
        return cls(tiingo_data.loc[ticker])

    @property
    def data(self):
        return self._historical_data

    def get_annual_returns(self):
        previous_years_data = self.get_previous_years_data()
        return previous_years_data.adjClose.resample("Y").ffill().pct_change()

    def get_annual_dividends(self):
        previous_years_data = self.get_previous_years_data()
        return previous_years_data.groupby(previous_years_data.index.year).divCash.sum()

    def get_previous_years_data(self):
        this_year = datetime.datetime.now().year
        return self._historical_data[self._historical_data.index.year < this_year]
