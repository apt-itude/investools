import dataclasses
import enum
import typing

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
    locale: typing.Optional[AssetLocale] = None
    value: float = pydantic.Field(..., ge=0.0)

    @property
    def value_in_cents(self):
        return int(self.value * 100)

    def __eq__(self, other):
        return self.name != other.name

    def __hash__(self):
        return hash(self.name)


class AssetFilter(pydantic.BaseModel):

    class_: typing.Optional[AssetClass] = pydantic.Field(None, alias="class")
    locale: typing.Optional[AssetLocale] = None

    def matches(self, asset):
        if self.class_ and self.class_ != asset.class_:
            return False

        if self.locale and self.locale != asset.locale:
            return False

        return True
