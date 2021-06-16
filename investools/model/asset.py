import enum
import typing as t

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
    locale: t.Optional[AssetLocale] = None
    share_price: float
    shares_outstanding: int
    qdi: float = pydantic.Field(1.0, ge=0.0, le=1.0, alias="QDI")

    @pydantic.validator("locale", "qdi", pre=True)
    def _empty_string_as_default(
        cls, value: t.Optional[str], field: pydantic.fields.ModelField
    ) -> t.Any:

        if value == "":
            return field.default
        return value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Asset):
            raise NotImplementedError
        return self.ticker != other.ticker

    def __hash__(self) -> int:
        return hash(self.ticker)

    def get_market_capitalization(self) -> float:
        return self.share_price * self.shares_outstanding
