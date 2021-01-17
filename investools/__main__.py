import pathlib

import click
import pulp
import tabulate
import yaml
from devtools import debug

from investools import model


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
@click.option(
    "--portfolio",
    "portfolio_path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
    default="portfolio.yaml",
)
def main(ctx, portfolio_path):
    ctx.obj = model.Portfolio.from_yaml_file(portfolio_path)


@main.command()
@click.pass_obj
@click.option("--drift-limit", type=float, default=1.0)
def rebalance(portfolio, drift_limit):
    problem = pulp.LpProblem(name="Rebalance", sense=pulp.const.LpMinimize)

    target_asset_quantities_per_account = [
        (
            account,
            asset,
            pulp.LpVariable(
                f"target_quantity_account_{account.id}_asset_{asset.name}",
                lowBound=0,
                cat="Integer",
            ),
        )
        for account in portfolio.accounts
        for asset in portfolio.assets
    ]

    assets_by_name = {asset.name: asset for asset in portfolio.assets}

    for account in portfolio.accounts:
        total_account_value = account.get_total_value_in_cents(assets_by_name)

        target_asset_quantities = [
            (asset, target_quantity)
            for inner_account, asset, target_quantity in target_asset_quantities_per_account
            if inner_account.id == account.id
        ]

        target_account_investments = [
            target_quantity * asset.value_in_cents
            for asset, target_quantity in target_asset_quantities
        ]

        problem += (
            pulp.lpSum(target_account_investments) == total_account_value,
            f"total_value_account_{account.id}",
        )

    total_portfolio_value = portfolio.get_total_value_in_cents()
    allocation_drifts = []

    for allocation in portfolio.allocations:
        matching_asset_names = {
            asset.name for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            target_quantity * asset.value_in_cents
            for _, asset, target_quantity in target_asset_quantities_per_account
            if asset.name in matching_asset_names
        ]

        matching_assets_total_investment = pulp.lpSum(matching_asset_investments)
        matching_assets_percentage = (
            matching_assets_total_investment * 100 / total_portfolio_value
        )
        matching_assets_drift = allocation.percentage - matching_assets_percentage
        problem += (
            matching_assets_drift <= drift_limit,
            f"drift_positive_allocation_{allocation.id}",
        )
        problem += (
            -matching_assets_drift <= drift_limit,
            f"drift_negative_allocation_{allocation.id}",
        )
        allocation_drifts.append(matching_assets_drift)

    problem += pulp.lpSum(allocation_drifts)

    problem.solve()

    print(f"Status: {problem.status}, {pulp.LpStatus[problem.status]}", end="\n\n")

    account_results = []
    for account in portfolio.accounts:
        for (
            inner_account,
            asset,
            target_quantity,
        ) in target_asset_quantities_per_account:
            if inner_account.id == account.id:
                current_quantity = account.get_asset_quantity(asset.name)
                delta = target_quantity.value() - current_quantity
                account_results.append(
                    [
                        account.name,
                        asset.name,
                        current_quantity,
                        target_quantity.value(),
                        delta,
                    ]
                )

    print(
        tabulate.tabulate(
            account_results,
            headers=[
                "Account",
                "Asset",
                "Current Quantity",
                "Target Quantity",
                "Delta",
            ],
        ),
        end="\n\n",
    )

    allocation_results = []
    for allocation in portfolio.allocations:
        matching_asset_names = {
            asset.name for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            asset_quantity.value() * asset.value_in_cents
            for _, asset, asset_quantity in target_asset_quantities_per_account
            if asset.name in matching_asset_names
        ]
        matching_assets_total_investment = sum(matching_asset_investments)
        matching_assets_percentage = (
            matching_assets_total_investment * 100 / total_portfolio_value
        )
        matching_assets_drift = allocation.percentage - matching_assets_percentage

        allocation_results.append(
            [
                allocation.name,
                allocation.percentage,
                matching_assets_percentage,
                matching_assets_drift,
            ]
        )

    print(
        tabulate.tabulate(
            allocation_results,
            headers=["Allocation", "Target %", "Actual %", "Drift %"],
            floatfmt=".2f",
        )
    )


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
