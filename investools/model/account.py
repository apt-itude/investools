import datetime
import enum
import typing as t

import pydantic

from .asset import Asset
from .base import BaseModel


class TaxationClass(enum.Enum):

    TAXABLE = "Taxable"
    TAX_DEFERRED = "TaxDeferred"
    TAX_EXEMPT = "TaxExempt"


class GoogleSheetDateTime(datetime.datetime):

    START_DATE = datetime.datetime(1899, 12, 30)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value):
        if not isinstance(value, int):
            raise TypeError("int required")

        return cls.START_DATE + datetime.timedelta(days=value)


class HoldTerm(enum.Enum):

    SHORT = enum.auto()
    LONG = enum.auto()


class AssetLot(BaseModel):

    ticker: str
    shares: float = pydantic.Field(0.0, ge=0.0)
    purchase_date: t.Optional[GoogleSheetDateTime]
    purchase_price: t.Optional[float]

    @property
    def days_held(self) -> t.Optional[int]:
        if self.purchase_date is None:
            return None

        delta = datetime.datetime.today() - self.purchase_date
        return delta.days

    @property
    def hold_term(self) -> t.Optional[HoldTerm]:
        if self.days_held is None:
            return None

        return HoldTerm.LONG if self.days_held > 365 else HoldTerm.SHORT


class Account(BaseModel):

    name: str
    taxation_class: TaxationClass
    withdrawal_year: int
    withdrawal_tax_rate: t.Optional[float] = pydantic.Field(None, ge=0.0, le=1.0)
    cash_balance: float = pydantic.Field(0.0, ge=0.0)
    asset_lots: t.List[AssetLot] = pydantic.Field(default_factory=list)

    @pydantic.validator("withdrawal_year")
    def _withdrawal_year_is_current_or_future(cls, withdrawal_year: int) -> int:
        this_year = datetime.datetime.now().year
        if withdrawal_year < this_year:
            raise ValueError("Withdrawal year cannot be in the past")
        return withdrawal_year

    @pydantic.validator("withdrawal_tax_rate", pre=True)
    def _empty_string_as_none(cls, value: t.Optional[float]) -> t.Optional[float]:

        if not value:
            return None
        return value

    @property
    def id(self) -> str:
        return self.name.replace(" ", "_")

    def get_years_until_withdrawal(self) -> int:
        this_year = datetime.datetime.now().year
        return self.withdrawal_year - this_year

    def get_total_value(self, assets: t.Iterable[Asset]) -> float:
        assets_by_ticker = {asset.ticker: asset for asset in assets}
        total_asset_value = sum(
            (lot.shares * assets_by_ticker[lot.ticker].share_price)
            for lot in self.asset_lots
        )
        return self.cash_balance + total_asset_value

    def get_total_asset_shares(self, ticker: str) -> float:
        return sum(lot.shares for lot in self.iterate_lots_for_asset(ticker))

    def iterate_lots_for_asset(self, ticker: str) -> t.Iterator[AssetLot]:
        for lot in self.asset_lots:
            if lot.ticker == ticker:
                yield lot
