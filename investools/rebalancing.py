import dataclasses
import functools
import typing

import pulp

from . import model, returns


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

    def get_target_shares(self):
        return self.target_shares_variable.value()

    def get_current_shares(self):
        return self.account.get_total_asset_shares(self.asset.ticker)

    def get_delta(self):
        return self.get_target_shares() - self.get_current_shares()

    def get_target_investment(self):
        return self.get_target_shares() * self.asset.share_price


def rebalance(portfolio: model.Portfolio) -> typing.List[Position]:
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
            matching_assets_drift <= portfolio.config.drift_limit,
            f"drift_within_positive_limit_allocation_{allocation.id}",
        )
        problem += (
            -matching_assets_drift <= portfolio.config.drift_limit,
            f"drift_within_negative_limit_allocation_{allocation.id}",
        )

    # Ensure there are no taxable asset sales
    for position in positions:
        if position.account.taxation_class is model.TaxationClass.TAXABLE:
            problem += (
                position.target_shares_variable >= position.get_current_shares(),
                f"no_taxable_sales_account_{position.account.id}_"
                f"asset_{position.asset.ticker}",
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
    positions: typing.List[Position],
) -> typing.List[pulp.LpVariable]:
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
            return_rate = returns.project_tax_deferred_rate(
                asset,
                tax_exempt_return_rate,
                position.account.get_years_until_withdrawal(),
                portfolio.config.preferential_tax_rate,
            )
        else:
            return_rate = tax_exempt_return_rate

        project_return_variables.append(
            position.target_shares_variable * asset.share_price * return_rate
        )
    return project_return_variables


class CannotRebalance(Exception):
    def __str__(self):
        return "The portfolio cannot be rebalanced with the given constraints"
