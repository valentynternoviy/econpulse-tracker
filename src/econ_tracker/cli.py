"""Command-line interface (econ-cli): database seeding, market collection, and reports."""

from __future__ import annotations

import asyncio
import json

import typer

from econ_tracker.api.deps import AppContainer
from econ_tracker.config import get_settings
from econ_tracker.logging_config import configure_logging
from econ_tracker.storage.database import Base
from econ_tracker.storage.seed import seed_database

app = typer.Typer(
    name="econ-cli",
    help="EconPulse CLI for seeding, data collection, and market analytics reports.",
    no_args_is_help=True,
)


@app.command()
def seed(
    if_empty: bool = typer.Option(
        False,
        "--if-empty",
        help="Skip seeding if items already exist in the database.",
    ),
    days: int = typer.Option(30, "--days", min=1, max=90, help="Days of historical snapshots."),
    create_tables: bool = typer.Option(
        False,
        "--create-tables",
        help="Ensure schema exists before seeding (useful for fresh SQLite dev DBs).",
    ),
) -> None:
    """Populate database with 320+ Warframe & Rust items and 30 days of price history."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=False)

    async def _run() -> dict[str, int]:
        container = AppContainer.build(settings)
        try:
            if create_tables:
                async with container.engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
            async with container.session_factory() as session:
                return await seed_database(session, if_empty=if_empty, days=days)
        finally:
            await container.shutdown()

    result = asyncio.run(_run())
    typer.echo(json.dumps(result, indent=2))


@app.command()
def collect(
    market_id: int | None = typer.Option(
        None,
        "--market-id",
        help="Collect from a specific market ID (default: all active markets in parallel).",
    ),
) -> None:
    """Trigger immediate data collection from configured external APIs."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=False)

    async def _run() -> list[dict[str, object]]:
        container = AppContainer.build(settings)
        try:
            runs = await container.collector_service.run_collection(market_id=market_id)
            return [r.model_dump(mode="json") for r in runs]
        finally:
            await container.shutdown()

    output = asyncio.run(_run())
    typer.echo(json.dumps(output, indent=2))


@app.command()
def report(
    game: str | None = typer.Option(
        None,
        "--game",
        help="Filter report by game code (warframe or rust).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print machine-readable JSON."),
) -> None:
    """Generate analytical market summary report (indices, top movers, spreads, rarities)."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=False)

    async def _run() -> tuple[dict[str, object], list[dict[str, object]]]:
        container = AppContainer.build(settings)
        try:
            async with container.session_factory() as session:
                overview = await container.analytics_service.get_overview(session, game=game)
                spreads = await container.analytics_service.get_spreads(
                    session, game=game, limit=5
                )
                return (
                    overview.model_dump(mode="json"),
                    [s.model_dump(mode="json") for s in spreads],
                )
        finally:
            await container.shutdown()

    overview_data, spreads_data = asyncio.run(_run())
    if as_json:
        typer.echo(json.dumps({"overview": overview_data, "top_spreads": spreads_data}, indent=2))
        return

    typer.echo("=== EconPulse Market Report ===")
    typer.echo(
        f"Items: {overview_data['total_items']} | "
        f"Snapshots: {overview_data['total_snapshots']} | "
        f"Offers: {overview_data['total_offers']} | "
        f"Market Cap: ${overview_data['total_market_value_usd']}"
    )
    typer.echo("\nTop Cross-Market Spreads:")
    for sp in spreads_data:
        typer.echo(
            f"  - {sp['name']} ({sp['game_code']}): "
            f"${sp['min_price']} -> ${sp['max_price']} (+{sp['spread_pct']}%)"
        )


if __name__ == "__main__":
    app()
