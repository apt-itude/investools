import enum
import typing as t

import pydantic

from .base import BaseModel


class AssetClass(enum.Enum):
    CASH = "Cash"
    EQUITY_US = "Equity_US"
    EQUITY_US_LARGE_CAP = "Equity_US_Large_Cap"
    EQUITY_US_MID_CAP = "Equity_US_Mid_Cap"
    EQUITY_US_SMALL_CAP = "Equity_US_Small_Cap"
    EQUITY_INTERNATIONAL = "Equity_International"
    EQUITY_INTERNATIONAL_DEVELOPED = "Equity_International_Developed"
    EQUITY_INTERNATIONAL_EMERGING = "Equity_International_Emerging"
    FIXED_INCOME = "Fixed_Income"
    REIT = "REIT"


class Asset(BaseModel):
    ticker: str
    class_: AssetClass
    share_price: float
    shares_outstanding: int
    qdi: float = pydantic.Field(1.0, ge=0.0, le=1.0, alias="QDI")

    @pydantic.validator("qdi", pre=True)
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
