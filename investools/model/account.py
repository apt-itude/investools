import datetime
import enum
import typing

import pydantic

from .base import BaseModel


class TaxationClass(enum.Enum):

    TAXABLE = "Taxable"
    TAX_DEFERRED = "TaxDeferred"
    TAX_EXEMPT = "TaxExempt"


class AssetLot(BaseModel):

    ticker: str
    shares: float = pydantic.Field(0.0, ge=0.0)
    # TODO purchase_date


class Account(BaseModel):

    name: str
    taxation_class: TaxationClass
    withdrawal_year: int
    withdrawal_tax_rate: typing.Optional[float] = pydantic.Field(None, ge=0.0, le=1.0)
    cash_balance: float = pydantic.Field(0.0, ge=0.0)
    asset_lots: typing.List[AssetLot] = pydantic.Field(default_factory=list)

    @pydantic.validator("withdrawal_year")
    def _withdrawal_year_is_current_or_future(cls, withdrawal_year):
        this_year = datetime.datetime.now().year
        if withdrawal_year < this_year:
            raise ValueError("Withdrawal year cannot be in the past")
        return withdrawal_year

    @pydantic.validator("withdrawal_tax_rate", pre=True)
    def _empty_string_as_none(cls, value):
        if not value:
            return None
        return value

    @property
    def id(self):
        return self.name.replace(" ", "_")

    def get_years_until_withdrawal(self):
        this_year = datetime.datetime.now().year
        return self.withdrawal_year - this_year

    def get_total_value(self, assets):
        assets_by_ticker = {asset.ticker: asset for asset in assets}
        total_asset_value = sum(
            (lot.shares * assets_by_ticker[lot.ticker].share_price)
            for lot in self.asset_lots
        )
        return self.cash_balance + total_asset_value

    def get_total_asset_shares(self, ticker):
        return sum(lot.shares for lot in self.iterate_lots_for_asset(ticker))

    def iterate_lots_for_asset(self, ticker):
        for lot in self.asset_lots:
            if lot.ticker == ticker:
                yield lot
