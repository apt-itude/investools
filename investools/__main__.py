import click
import pulp
import tabulate
from devtools import debug

from investools import model, returns, sheets


@click.group(
    context_settings={
        "auto_envvar_prefix": "INVESTOOLS",
        "help_option_names": ["-h", "--help"],
    }
)
@click.pass_context
@click.option(
    "-s",
    "--google-sheet-id",
    show_envvar=True,
    show_default=True,
)
def main(ctx, google_sheet_id):
    sheet_client = sheets.get_client()
    sheet = sheet_client.open_by_key(google_sheet_id)
    ctx.obj = sheets.build_portfolio(sheet)


@main.command()
@click.pass_obj
def print_portfolio(portfolio):
    debug(portfolio)


@main.command()
@click.pass_obj
@click.option(
    "-y",
    "--years",
    default=30,
    show_envvar=True,
    show_default=True,
)
def project_returns(portfolio, years):
    tax_exempt_return_rates_by_asset = returns.project_tax_exempt_rates(
        portfolio.assets
    )

    return_rates = []
    for asset in portfolio.assets:
        tax_exempt_rate = tax_exempt_return_rates_by_asset[asset.ticker]
        tax_deferred_rate = returns.project_tax_deferred_rate(
            asset,
            tax_exempt_rate,
            years,
            portfolio.config.preferential_tax_rate,
        )
        taxable_rate = returns.project_taxable_rate(
            asset,
            tax_exempt_rate,
            years,
            portfolio.config.ordinary_tax_rate,
            portfolio.config.preferential_tax_rate,
        )
        return_rates.append(
            [asset.ticker, tax_exempt_rate, tax_deferred_rate, taxable_rate]
        )

    print(
        tabulate.tabulate(
            return_rates, headers=["Asset", "Tax-exempt", "Tax-deferred", "Taxable"]
        )
    )


@main.command()
@click.pass_obj
def rebalance(portfolio):
    tax_exempt_return_rates_by_asset = returns.project_tax_exempt_rates(
        portfolio.assets
    )

    problem = pulp.LpProblem(name="Rebalance", sense=pulp.const.LpMaximize)

    target_asset_quantities_per_account = [
        (
            account,
            asset,
            pulp.LpVariable(
                f"target_quantity_account_{account.id}_asset_{asset.ticker}",
                lowBound=0,
                cat="Integer",
            ),
        )
        for account in portfolio.accounts
        for asset in portfolio.assets
    ]

    projected_asset_returns = []

    for account in portfolio.accounts:
        total_account_value = account.get_total_value(portfolio.assets)

        target_asset_quantities = [
            (asset, target_quantity)
            for inner_account, asset, target_quantity in target_asset_quantities_per_account
            if inner_account.id == account.id
        ]

        target_account_investments = [
            target_quantity * asset.share_price
            for asset, target_quantity in target_asset_quantities
        ]

        problem += (
            pulp.lpSum(target_account_investments) <= total_account_value,
            f"total_value_account_{account.id}",
        )

        if account.taxation_class is model.TaxationClass.TAXABLE:
            for asset, target_quantity in target_asset_quantities:
                current_quantity = account.get_total_asset_shares(asset.ticker)
                problem += (
                    target_quantity >= current_quantity,
                    f"no_taxable_sales_account_{account.id}_asset_{asset.ticker}",
                )

        for asset, target_quantity in target_asset_quantities:
            tax_exempt_return_rate = tax_exempt_return_rates_by_asset[asset.ticker]
            if account.taxation_class is model.TaxationClass.TAXABLE:
                return_rate = returns.project_taxable_rate(
                    asset,
                    tax_exempt_return_rate,
                    account.get_years_until_withdrawal(),
                    portfolio.config.ordinary_tax_rate,
                    portfolio.config.preferential_tax_rate,
                )
            elif account.taxation_class is model.TaxationClass.TAX_DEFERRED:
                return_rate = returns.project_tax_deferred_rate(
                    asset,
                    tax_exempt_return_rate,
                    account.get_years_until_withdrawal(),
                    portfolio.config.preferential_tax_rate,
                )
            else:
                return_rate = tax_exempt_return_rate

            projected_return = target_quantity * asset.share_price * return_rate

            projected_asset_returns.append(projected_return)

    total_portfolio_value = portfolio.get_total_value()
    allocation_drifts = []

    for allocation in portfolio.allocations:
        matching_asset_tickers = {
            asset.ticker for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            target_quantity * asset.share_price
            for _, asset, target_quantity in target_asset_quantities_per_account
            if asset.ticker in matching_asset_tickers
        ]

        matching_assets_total_investment = pulp.lpSum(matching_asset_investments)
        matching_assets_proportion = (
            matching_assets_total_investment / total_portfolio_value
        )
        matching_assets_drift = allocation.proportion - matching_assets_proportion
        problem += (
            matching_assets_drift <= portfolio.config.drift_limit,
            f"drift_positive_allocation_{allocation.id}",
        )
        problem += (
            -matching_assets_drift <= portfolio.config.drift_limit,
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
                current_quantity = account.get_total_asset_shares(asset.ticker)
                delta = target_quantity.value() - current_quantity
                account_results.append(
                    [
                        account.name,
                        asset.ticker,
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
        matching_asset_tickers = {
            asset.ticker for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            asset_quantity.value() * asset.share_price
            for _, asset, asset_quantity in target_asset_quantities_per_account
            if asset.ticker in matching_asset_tickers
        ]
        matching_assets_total_investment = sum(matching_asset_investments)
        matching_assets_proportion = (
            matching_assets_total_investment / total_portfolio_value
        )
        matching_assets_drift = allocation.proportion - matching_assets_proportion

        allocation_results.append(
            [
                allocation.name,
                allocation.proportion * 100,
                matching_assets_proportion * 100,
                matching_assets_drift * 100,
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
