import os
import pathlib
import typing

import pydantic
import yaml

from .account import Account
from .allocation import PercentageAllocation
from .asset import Asset


class Portfolio(pydantic.BaseModel):

    allocations: typing.List[PercentageAllocation]
    assets: typing.List[Asset]
    accounts: typing.List[Account]

    @pydantic.validator("allocations")
    def validate_allocation_percentages(cls, allocations):
        if not allocations:
            return allocations

        total_percentage = sum(allocation.percentage for allocation in allocations)

        if total_percentage != 100:
            raise ValueError(f"Total percentage is {total_percentage}; must be 100")

        return allocations

    @classmethod
    def from_yaml_file(cls, path: os.PathLike):
        data = yaml.safe_load(pathlib.Path(path).read_text())
        return cls.parse_obj(data)

    def get_total_value_in_cents(self):
        assets_by_name = {asset.name: asset for asset in self.assets}
        return sum(
            account.get_total_value_in_cents(assets_by_name)
            for account in self.accounts
        )
