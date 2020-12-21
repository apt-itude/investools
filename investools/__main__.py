import pathlib

import click
import pulp
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
    account_0 = portfolio.accounts[0]
    all_assets = portfolio.get_asset_set()
    assets_by_name = all_assets.to_dict()
    total_value_account_0 = account_0.get_total_value(assets_by_name)

    target_asset_quantities = {
        asset.name: pulp.LpVariable(
            f"target_quantity_asset_{asset.name}", lowBound=0, cat="Integer"
        )
        for asset in all_assets
    }

    target_asset_investments = {
        asset.name: target_asset_quantities[asset.name] * asset.value
        for asset in all_assets
    }

    problem = pulp.LpProblem(name="Allocate", sense=pulp.const.LpMinimize)

    problem += (
        pulp.lpSum(target_asset_investments.values()) == total_value_account_0,
        "total_value_account_0",
    )

    allocation_drifts = []

    for i, allocation in enumerate(portfolio.allocations):
        print(f"Allocation: {allocation}")

        matching_assets = all_assets.filter(allocation)
        print(f"Matching assets: {[asset.name for asset in matching_assets]}")

        matching_assets_total_investment = pulp.lpSum(
            [target_asset_investments[asset.name] for asset in matching_assets]
        )
        matching_assets_percentage = (
            matching_assets_total_investment * 100 / total_value_account_0
        )
        matching_assets_drift = allocation.percentage - matching_assets_percentage
        problem += (
            matching_assets_drift <= drift_limit,
            f"drift_positive_allocation_{i}",
        )
        problem += (
            -matching_assets_drift <= drift_limit,
            f"drift_negative_allocation_{i}",
        )
        allocation_drifts.append(matching_assets_drift)

    problem += pulp.lpSum(allocation_drifts)

    problem.solve()

    print(f"Status: {problem.status}, {pulp.LpStatus[problem.status]}")

    print(f"Objective: {problem.objective.value()}")

    print("Variables:")
    for var in problem.variables():
        print(f"{var.name}: {var.value()}")

    print("Constraints:")
    for name, constraint in problem.constraints.items():
        print(f"{name}: {constraint.value()}")


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
