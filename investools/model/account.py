import dataclasses
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
    cash_balance: float = pydantic.Field(0.0, ge=0.0)
    asset_lots: typing.List[AssetLot] = pydantic.Field(default_factory=list)

    @pydantic.validator("withdrawal_year")
    def _withdrawal_year_is_current_or_future(cls, withdrawal_year):
        this_year = datetime.datetime.now().year
        if withdrawal_year < this_year:
            raise ValueError("Withdrawal year cannot be in the past")
        return withdrawal_year

    @property
    def id(self):
        return self.name.replace(" ", "_")

    @property
    def cash_balance_in_cents(self):
        return int(self.cash_balance * 100)

    def get_years_until_withdrawal(self):
        this_year = datetime.datetime.now().year
        return self.withdrawal_year - this_year

    def get_total_value_in_cents(self, assets):
        assets_by_ticker = {asset.ticker: asset for asset in assets}
        total_asset_value_in_cents = sum(
            (lot.shares * assets_by_ticker[lot.ticker].get_share_price_in_cents())
            for lot in self.asset_lots
        )
        return round(self.cash_balance_in_cents + total_asset_value_in_cents)

    def get_total_asset_shares(self, ticker):
        return sum(lot.shares for lot in self.iterate_lots_for_asset(ticker))

    def iterate_lots_for_asset(self, ticker):
        for lot in self.asset_lots:
            if lot.ticker == ticker:
                yield lot
