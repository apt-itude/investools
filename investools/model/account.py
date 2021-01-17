import enum
import typing

import pydantic


class TaxationClass(enum.Enum):

    TAXABLE = "taxable"
    TAX_DEFERRED = "tax-deferred"
    TAX_EXEMPT = "tax-exempt"


class AssetLot(pydantic.BaseModel):

    asset: str
    quantity: float = pydantic.Field(0.0, ge=0.0)
    # TODO purchase_date


class Account(pydantic.BaseModel):

    name: str
    taxation_class: TaxationClass
    asset_lots: typing.List[AssetLot] = pydantic.Field(default_factory=list)

    @property
    def id(self):
        return self.name.replace(" ", "_")

    def get_total_value_in_cents(self, assets_by_name):
        return round(
            sum(
                (lot.quantity * assets_by_name[lot.asset].value_in_cents)
                for lot in self.asset_lots
            )
        )

    def get_asset_quantity(self, asset_name):
        return sum(lot.quantity for lot in self.asset_lots if lot.asset == asset_name)
