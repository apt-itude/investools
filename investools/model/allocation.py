import typing

import pydantic

from .asset import AssetClass, AssetLocale
from .base import BaseModel


class Allocation(BaseModel):

    name: str
    proportion: float = pydantic.Field(0.0, ge=0.0, le=1.0)
    asset_class: typing.Optional[AssetClass] = None
    asset_locale: typing.Optional[AssetLocale] = None

    @pydantic.validator("asset_class", "asset_locale", pre=True)
    def _empty_string_as_none(cls, value):
        if not value:
            return None
        return value

    @property
    def id(self):
        return self.name.replace(" ", "_")

    def matches(self, asset):
        if self.asset_class and self.asset_class != asset.class_:
            return False

        if self.asset_locale and self.asset_locale != asset.locale:
            return False

        return True
