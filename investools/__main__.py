import pathlib

import click
import pandas
import pandas_datareader
import pulp
import tabulate
import yaml
from devtools import debug

from investools import blacklitterman, model


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
def estimate_returns(portfolio):
    non_cash_assets = [
        asset for asset in portfolio.assets if asset.class_ is not model.AssetClass.CASH
    ]
    expected_return_rates_by_asset = _calculate_expected_return_rates(non_cash_assets)

    return_rates = []
    for asset in non_cash_assets:
        tax_exempt_rate = expected_return_rates_by_asset[asset.name]
        tax_deferred_rate = asset.project_annualized_tax_deferred_return_rate(
            tax_exempt_rate, 30, 0.2
        )
        taxable_rate = asset.project_annualized_taxable_return_rate(
            tax_exempt_rate, 30, 0.3, 0.2
        )
        return_rates.append([tax_exempt_rate, tax_deferred_rate, taxable_rate])

    print(
        tabulate.tabulate(
            return_rates, headers=["Tax-exempt", "Tax-deferred", "Taxable"]
        )
    )


def _calculate_expected_return_rates(non_cash_assets):
    acwi = model.Asset.parse_obj({"name": "ACWI", "class": "equity"})
    market_prices = acwi.get_historical_data().adjClose
    risk_aversion = blacklitterman.market_implied_risk_aversion(market_prices)

    market_caps_by_asset = {
        asset.name: asset.get_market_capitalization() for asset in non_cash_assets
    }
    annual_returns_by_asset = {
        asset.name: asset.get_annual_returns() for asset in non_cash_assets
    }
    covariance_matrix = pandas.DataFrame(annual_returns_by_asset).cov()
    return blacklitterman.market_implied_prior_returns(
        market_caps_by_asset, risk_aversion, covariance_matrix
    )


@main.command()
@click.pass_obj
@click.option("--drift-limit", type=float, default=0.1)
@click.option("--preferential-tax-rate", type=float, default=(0.15 + 0.5))
@click.option("--ordinary-tax-rate", type=float, default=(0.32 + 0.12))
def rebalance(portfolio, drift_limit, preferential_tax_rate, ordinary_tax_rate):
    non_cash_assets = [
        asset for asset in portfolio.assets if asset.class_ is not model.AssetClass.CASH
    ]
    expected_return_rates_by_asset = _calculate_expected_return_rates(non_cash_assets)

    problem = pulp.LpProblem(name="Rebalance", sense=pulp.const.LpMaximize)

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

    projected_asset_returns = []

    assets_by_name = {asset.name: asset for asset in portfolio.assets}

    for account in portfolio.accounts:
        total_account_value = account.get_total_value_in_cents(assets_by_name)

        target_asset_quantities = [
            (asset, target_quantity)
            for inner_account, asset, target_quantity in target_asset_quantities_per_account
            if inner_account.id == account.id
        ]

        target_account_investments = [
            target_quantity * asset.get_share_price_in_cents()
            for asset, target_quantity in target_asset_quantities
        ]

        problem += (
            pulp.lpSum(target_account_investments) == total_account_value,
            f"total_value_account_{account.id}",
        )

        if account.taxation_class is model.TaxationClass.TAXABLE:
            for asset, target_quantity in target_asset_quantities:
                if asset.class_ is not model.AssetClass.CASH:
                    current_quantity = account.get_asset_quantity(asset.name)
                    problem += (
                        target_quantity >= current_quantity,
                        f"no_taxable_sales_account_{account.id}_asset_{asset.name}",
                    )

        for asset, target_quantity in target_asset_quantities:
            if asset.class_ is model.AssetClass.CASH:
                continue

            tax_exempt_return_rate = expected_return_rates_by_asset[asset.name]
            if account.taxation_class is model.TaxationClass.TAXABLE:
                return_rate = asset.project_annualized_taxable_return_rate(
                    return_rate=tax_exempt_return_rate,
                    years=account.get_years_until_withdrawal(),
                    ordinary_tax_rate=ordinary_tax_rate,
                    preferential_tax_rate=preferential_tax_rate,
                )
            elif account.taxation_class is model.TaxationClass.TAX_DEFERRED:
                return_rate = asset.project_annualized_tax_deferred_return_rate(
                    return_rate=tax_exempt_return_rate,
                    years=account.get_years_until_withdrawal(),
                    preferential_tax_rate=preferential_tax_rate,
                )
            else:
                return_rate = tax_exempt_return_rate

            projected_return = (
                target_quantity * asset.get_share_price_in_cents() * return_rate
            )

            projected_asset_returns.append(projected_return)

    total_portfolio_value = portfolio.get_total_value_in_cents()
    allocation_drifts = []

    for allocation in portfolio.allocations:
        matching_asset_names = {
            asset.name for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            target_quantity * asset.get_share_price_in_cents()
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

    problem += pulp.lpSum(projected_asset_returns)

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
            asset_quantity.value() * asset.get_share_price_in_cents()
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
