import typing

import pydantic

from .account import Account
from .allocation import Allocation
from .asset import Asset
from .base import BaseModel


class Portfolio(BaseModel):

    allocations: typing.List[Allocation]
    accounts: typing.List[Account]
    assets: typing.List[Asset]

    @pydantic.validator("allocations")
    def _allocation_proportions_sum_to_one(cls, allocations):
        if not allocations:
            return allocations

        proportions_sum = sum(allocation.proportion for allocation in allocations)

        if proportions_sum != 1:
            raise ValueError(f"Sum of proportions is {proportions_sum}; must be 1")

        return allocations

    def get_total_value_in_cents(self):
        return sum(
            account.get_total_value_in_cents(self.assets) for account in self.accounts
        )
