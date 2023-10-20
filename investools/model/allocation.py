import typing as t

import pydantic

from .asset import Asset, AssetClass
from .base import BaseModel


class Allocation(BaseModel):
    name: str
    proportion: float = pydantic.Field(0.0, ge=0.0, le=1.0)
    asset_class: t.Optional[AssetClass] = None

    @pydantic.validator("asset_class", pre=True)
    def _empty_string_as_none(cls, value: t.Optional[str]) -> t.Optional[str]:
        if not value:
            return None
        return value

    @property
    def id(self) -> str:
        return self.name.replace(" ", "_")

    def matches(self, asset: Asset) -> bool:
        if self.asset_class and self.asset_class != asset.class_:
            return False

        return True
