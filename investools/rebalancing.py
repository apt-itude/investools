import dataclasses
import enum
import functools
import typing as t

import pulp

from . import model, returns


class AllowedSales(enum.Enum):

    NONE = "none"
    TAX_FREE = "tax-free"
    LONG_TERM = "long-term"
    ALL = "all"


@dataclasses.dataclass
class Sale:

    share_count: float
    sale_price: float
    asset_lot: model.AssetLot

    @property
    def cost_basis(self) -> t.Optional[float]:
        if self.asset_lot.purchase_price is None:
            return None

        return self.share_count * self.asset_lot.purchase_price

    @property
    def proceeds(self) -> float:
        return self.share_count * self.sale_price

    @property
    def capital_gains(self) -> t.Optional[float]:
        if self.cost_basis is None:
            return None

        return self.proceeds - self.cost_basis


@dataclasses.dataclass
class Position:

    account: model.Account
    asset: model.Asset

    @functools.cached_property
    def target_shares_variable(self) -> pulp.LpVariable:
        return pulp.LpVariable(
            f"target_shares_account_{self.account.id}_asset_{self.asset.ticker}",
            lowBound=0,
            cat="Integer",
        )

    def get_target_shares(self) -> int:
        return self.target_shares_variable.value()  # type: ignore

    def get_current_shares(self) -> float:
        return self.account.get_total_asset_shares(self.asset.ticker)

    def get_delta(self) -> float:
        return self.get_target_shares() - self.get_current_shares()

    def get_target_investment(self) -> float:
        return self.get_target_shares() * self.asset.share_price

    def get_short_term_share_count(self) -> float:
        return sum(
            lot.shares
            for lot in self._iter_asset_lots()
            if lot.hold_term is model.HoldTerm.SHORT
        )

    def _iter_asset_lots(self) -> t.Iterator[model.AssetLot]:
        for lot in self.account.asset_lots:
            if lot.ticker == self.asset.ticker:
                yield lot

    def generate_sales(self, allowed: AllowedSales) -> t.Iterator[Sale]:
        delta = self.get_delta()
        remaining_shares_to_sell = abs(delta) if delta < 0 else 0

        lot_iter = iter(
            sorted(
                [
                    lot
                    for lot in self._iter_asset_lots()
                    if allowed is AllowedSales.ALL
                    or lot.hold_term is not model.HoldTerm.SHORT
                ],
                key=_asset_lot_sale_order_sort_key,
                reverse=True,
            )
        )

        while remaining_shares_to_sell:
            try:
                lot_to_sell_from = next(lot_iter)
            except StopIteration:
                return

            share_count = min(remaining_shares_to_sell, lot_to_sell_from.shares)
            yield Sale(
                share_count=share_count,
                sale_price=self.asset.share_price,
                asset_lot=lot_to_sell_from,
            )
            remaining_shares_to_sell -= share_count


def _asset_lot_sale_order_sort_key(
    lot: model.AssetLot,
) -> t.Tuple[bool, t.Optional[float]]:
    """
    Sell assets starting with the highest purchase price first to minimize capital
    gains / maximize capital losses
    """
    if not lot.purchase_price:
        # Separate lots without a purchase price into their own section
        return False, None

    return True, lot.purchase_price


def rebalance(
    portfolio: model.Portfolio, allowed_sales: AllowedSales
) -> t.List[Position]:
    drift_limit = 0.0001
    while True:
        try:
            return _try_rebalance(portfolio, drift_limit, allowed_sales)
        except CannotRebalance:
            drift_limit = drift_limit * 2
            if drift_limit > portfolio.config.drift_limit:
                raise


def _try_rebalance(
    portfolio: model.Portfolio,
    drift_limit: float,
    allowed_sales: AllowedSales,
) -> t.List[Position]:

    problem = pulp.LpProblem(name="Rebalance", sense=pulp.const.LpMaximize)

    positions = [
        Position(account, asset)
        for account in portfolio.accounts
        for asset in portfolio.assets
    ]

    # Ensure the total investment in every account does not exceed its current value
    for account in portfolio.accounts:
        total_account_value = account.get_total_value(portfolio.assets)

        account_positions = [
            position for position in positions if position.account.id == account.id
        ]

        account_investments = [
            position.target_shares_variable * position.asset.share_price
            for position in account_positions
        ]

        problem += (
            pulp.lpSum(account_investments) <= total_account_value,
            f"investments_dont_exceed_value_account_{account.id}",
        )

    # Ensure each allocation is within the drift limit of its target proportion
    total_portfolio_value = portfolio.get_total_value()

    for allocation in portfolio.allocations:
        matching_asset_tickers = {
            asset.ticker for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            position.target_shares_variable * position.asset.share_price
            for position in positions
            if position.asset.ticker in matching_asset_tickers
        ]

        matching_assets_total_investment = pulp.lpSum(matching_asset_investments)
        matching_assets_proportion = (
            matching_assets_total_investment / total_portfolio_value
        )
        matching_assets_drift = allocation.proportion - matching_assets_proportion
        problem += (
            matching_assets_drift <= drift_limit,
            f"drift_within_positive_limit_allocation_{allocation.id}",
        )
        problem += (
            -matching_assets_drift <= drift_limit,
            f"drift_within_negative_limit_allocation_{allocation.id}",
        )

    # Constrain based on allowed sale type
    for position in positions:
        if allowed_sales is AllowedSales.NONE:
            problem += (
                position.target_shares_variable >= position.get_current_shares(),
                f"no_sales_account_{position.account.id}_asset_{position.asset.ticker}",
            )
        elif (
            allowed_sales is AllowedSales.TAX_FREE
            and position.account.taxation_class is model.TaxationClass.TAXABLE
        ):
            problem += (
                position.target_shares_variable >= position.get_current_shares(),
                f"no_taxable_sales_account_{position.account.id}_asset_{position.asset.ticker}",
            )
        elif (
            allowed_sales is AllowedSales.LONG_TERM
            and position.account.taxation_class is model.TaxationClass.TAXABLE
        ):
            short_term_share_count = position.get_short_term_share_count()
            if short_term_share_count > 0:
                problem += (
                    position.target_shares_variable >= short_term_share_count,
                    f"no_short_term_sales_account_{position.account.id}_asset_{position.asset.ticker}",
                )

    projected_position_return_variables = _get_projected_position_return_variables(
        portfolio, positions
    )
    problem += pulp.lpSum(projected_position_return_variables)

    problem.solve()

    if problem.status != 1:
        raise CannotRebalance()

    return positions


def _get_projected_position_return_variables(
    portfolio: model.Portfolio,
    positions: t.List[Position],
) -> t.List[pulp.LpVariable]:

    tax_exempt_return_rates_by_asset = returns.project_tax_exempt_rates(
        portfolio.assets
    )
    project_return_variables = []
    for position in positions:
        asset = position.asset

        tax_exempt_return_rate = tax_exempt_return_rates_by_asset[asset.ticker]
        if position.account.taxation_class is model.TaxationClass.TAXABLE:
            return_rate = returns.project_taxable_rate(
                asset,
                tax_exempt_return_rate,
                position.account.get_years_until_withdrawal(),
                portfolio.config.ordinary_tax_rate,
                portfolio.config.preferential_tax_rate,
            )
        elif position.account.taxation_class is model.TaxationClass.TAX_DEFERRED:
            tax_rate = (
                portfolio.config.ordinary_tax_rate
                if position.account.withdrawal_tax_rate is None
                else position.account.withdrawal_tax_rate
            )
            return_rate = returns.project_tax_deferred_rate(
                asset,
                tax_exempt_return_rate,
                position.account.get_years_until_withdrawal(),
                tax_rate,
            )
        else:
            return_rate = tax_exempt_return_rate

        project_return_variables.append(
            position.target_shares_variable * asset.share_price * return_rate
        )
    return project_return_variables


class CannotRebalance(Exception):
    def __str__(self) -> str:
        return "The portfolio cannot be rebalanced with the given constraints"
