import typing

import pydantic

from .asset import AssetFilter


class PercentageAllocation(AssetFilter):

    percentage: float = pydantic.Field(0.0, ge=0.0, le=100.0)
