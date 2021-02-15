import enum
import typing

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
    share_price: float
    shares_outstanding: int
    qdi: float = pydantic.Field(1.0, ge=0.0, le=1.0)

    @pydantic.validator("locale", pre=True)
    def _empty_string_as_none(cls, value):
        if not value:
            return None
        return value

    def __eq__(self, other):
        return self.ticker != other.ticker

    def __hash__(self):
        return hash(self.ticker)

    def get_market_capitalization(self):
        return self.share_price * self.shares_outstanding
