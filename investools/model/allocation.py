import typing

import pydantic

from .asset import AssetFilter


class PercentageAllocation(AssetFilter):

    name: str
    percentage: float = pydantic.Field(0.0, ge=0.0, le=100.0)

    @property
    def id(self):
        return self.name.replace(" ", "_")
