import sys

import click
import tabulate

try:
    from devtools import debug
except ImportError:
    debug = print

from investools import model, rebalancing, returns, sheets


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
def main(ctx: click.Context, google_sheet_id: str) -> None:
    sheet_client = sheets.get_client()
    sheet = sheet_client.open_by_key(google_sheet_id)
    ctx.obj = sheets.build_portfolio(sheet)


@main.command()
@click.pass_obj
def print_portfolio(portfolio: model.Portfolio) -> None:
    debug(portfolio)


@main.command()
@click.pass_obj
@click.option(
    "-y",
    "--years",
    type=int,
    default=30,
    show_envvar=True,
    show_default=True,
)
def project_returns(portfolio: model.Portfolio, years: int) -> None:
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
            portfolio.config.ordinary_tax_rate,
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
@click.option(
    "--no-sales",
    is_flag=True,
    default=False,
    help=(
        "Disallow asset sales (generally only works when rebalancing after adding cash)"
    ),
    show_default=True,
)
def rebalance(portfolio: model.Portfolio, no_sales: bool) -> None:
    try:
        positions = rebalancing.rebalance(portfolio, no_sales=no_sales)
    except rebalancing.CannotRebalance as err:
        sys.exit(str(err))

    print(
        tabulate.tabulate(
            [
                (
                    position.account.name,
                    position.asset.ticker,
                    position.get_current_shares(),
                    position.get_target_shares(),
                    position.get_delta(),
                )
                for position in positions
            ],
            headers=[
                "Account",
                "Asset",
                "Current Shares",
                "Target Shares",
                "Delta",
            ],
        ),
        end="\n\n",
    )

    total_portfolio_value = portfolio.get_total_value()
    allocation_results = []
    for allocation in portfolio.allocations:
        matching_asset_tickers = {
            asset.ticker for asset in portfolio.assets if allocation.matches(asset)
        }

        matching_asset_investments = [
            position.get_target_investment()
            for position in positions
            if position.asset.ticker in matching_asset_tickers
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
