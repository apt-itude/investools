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
def summary(portfolio: model.Portfolio) -> None:
    total_portfolio_value = portfolio.get_total_value()

    positions = [
        rebalancing.Position(account, asset)
        for account in portfolio.accounts
        for asset in portfolio.assets
    ]

    print("=========")
    print("POSITIONS")
    print("=========")
    print()
    print(
        tabulate.tabulate(
            [
                (
                    position.account.name,
                    position.asset.ticker,
                    position.get_current_shares(),
                    position.asset.share_price,
                    position.get_current_investment(),
                )
                for position in positions
            ],
            headers=[
                "Account",
                "Asset",
                "Current Shares",
                "Current Share Price",
                "Current Investment",
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
            position.get_current_investment()
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

    print("===========")
    print("ALLOCATIONS")
    print("===========")
    print()
    print(
        tabulate.tabulate(
            allocation_results,
            headers=["Allocation", "Target %", "Actual %", "Drift %"],
            floatfmt=".2f",
        )
    )


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
    "-s",
    "--sales",
    "allowed_sales_str",
    type=click.Choice([e.value for e in rebalancing.AllowedSales]),
    default=rebalancing.AllowedSales.TAX_FREE.value,
    help="Which type of asset sales to allow",
    show_default=True,
)
@click.option(
    "-t",
    "--max-time",
    type=int,
    default=60,
    help="Max number of seconds to wait for optimal solution",
    show_default=True,
)
def rebalance(
    portfolio: model.Portfolio,
    allowed_sales_str: str,
    max_time: int,
) -> None:
    allowed_sales = rebalancing.AllowedSales(allowed_sales_str)

    try:
        positions = rebalancing.rebalance(portfolio, allowed_sales, max_time)
    except rebalancing.CannotRebalance as err:
        sys.exit(str(err))

    print("=========")
    print("REBALANCE")
    print("=========")
    print()
    print(
        tabulate.tabulate(
            [
                (
                    position.account.name,
                    position.asset.ticker,
                    position.get_current_shares(),
                    position.get_target_shares(),
                    position.get_delta(),
                    position.asset.share_price,
                    (position.get_delta() * position.asset.share_price),
                )
                for position in positions
            ],
            headers=[
                "Account",
                "Asset",
                "Current Shares",
                "Target Shares",
                "Delta",
                "Current Share Price",
                "Estimated Trade Amount",
            ],
        ),
        end="\n\n",
    )

    net_ltcg = 0.0
    net_stcg = 0.0
    sale_rows = []
    for position in positions:
        for sale in position.generate_sales(allowed_sales):
            sale_rows.append(
                (
                    position.account.name,
                    position.asset.ticker,
                    sale.asset_lot.purchase_date,
                    sale.asset_lot.shares,
                    sale.share_count,
                    sale.cost_basis,
                    sale.proceeds,
                    sale.capital_gains,
                    sale.asset_lot.hold_term.name if sale.asset_lot.hold_term else None,
                )
            )
            if sale.capital_gains:
                if sale.asset_lot.hold_term is model.HoldTerm.LONG:
                    net_ltcg += sale.capital_gains
                else:
                    net_stcg += sale.capital_gains

    print("=====")
    print("SALES")
    print("=====")
    print()
    print(
        tabulate.tabulate(
            sale_rows,
            headers=[
                "Account",
                "Asset",
                "Lot Purchase Date",
                "Lot Shares",
                "Shares to Sell",
                "Cost Basis",
                "Proceeds",
                "Capital Gain/Loss",
                "Hold Term",
            ],
        ),
        end="\n\n",
    )
    print(f"Net LTCG: {net_ltcg}")
    print(f"Net STCG: {net_stcg}", end="\n\n")

    print("=========")
    print("PURCHASES")
    print("=========")
    print()
    print(
        tabulate.tabulate(
            [
                (
                    position.account.name,
                    position.asset.ticker,
                    position.get_delta(),
                    (position.get_delta() * position.asset.share_price),
                )
                for position in positions
                if position.get_delta() > 0
            ],
            headers=[
                "Account",
                "Asset",
                "Shares to Purchase",
                "Cost",
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

    print("=====================")
    print("RESULTING ALLOCATIONS")
    print("=====================")
    print()
    print(
        tabulate.tabulate(
            allocation_results,
            headers=["Allocation", "Target %", "Actual %", "Drift %"],
            floatfmt=".2f",
        )
    )


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
