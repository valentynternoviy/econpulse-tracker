"""Integration tests for catalog filtering, pagination, CSV export, analytics, and watchlist."""

from __future__ import annotations

import httpx
import pytest

from econ_tracker.api.deps import AppContainer
from tests.conftest import auth_headers


@pytest.mark.integration
async def test_catalog_pagination_facets_card_and_csv_export(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    client, _ = seeded_app

    # 1. Games endpoint with market totals
    games = (await client.get("/api/v1/games")).json()
    assert {g["code"] for g in games} == {"warframe", "rust"}
    assert sum(g["items_count"] for g in games) >= 300

    # 2. Category facets for Rust include clothing -> hoodie and deployables -> furnace
    facets = (await client.get("/api/v1/categories?game=rust")).json()
    by_cat = {f["code"]: {s["code"] for s in f["subcategories"]} for f in facets}
    assert "hoodie" in by_cat["clothing"]
    assert "furnace" in by_cat["deployables"]

    # 3. Pagination stability: page 1 and page 2 must have zero overlapping IDs
    p1 = (await client.get("/api/v1/items?game=rust&sort=price_desc&page=1&page_size=20")).json()
    p2 = (await client.get("/api/v1/items?game=rust&sort=price_desc&page=2&page_size=20")).json()
    ids1 = {it["id"] for it in p1["items"]}
    ids2 = {it["id"] for it in p2["items"]}
    assert len(ids1) == 20
    assert len(ids2) == 20
    assert ids1.isdisjoint(ids2)

    # 4. Server-side search + subcategory filter
    hoodies = (
        await client.get("/api/v1/items?game=rust&item_type=clothing&subcategory=hoodie&q=blackout")
    ).json()
    assert hoodies["total"] >= 1
    assert all("blackout" in it["name"].lower() for it in hoodies["items"])

    # 5. Item card with cross-market quotes & spread
    item_id = hoodies["items"][0]["id"]
    card = (await client.get(f"/api/v1/items/{item_id}")).json()
    assert len(card["markets"]) == 2
    assert card["cheapest_price"] is not None

    # 6. History JSON & CSV export
    hist_json = await client.get(f"/api/v1/items/{item_id}/prices?step=day")
    assert hist_json.status_code == 200
    assert len(hist_json.json()["points"]) >= 5

    hist_csv = await client.get(f"/api/v1/items/{item_id}/prices?step=week&format=csv")
    assert hist_csv.status_code == 200
    assert hist_csv.headers["content-type"].startswith("text/csv")
    assert "bucket_utc,min_price_usd" in hist_csv.text

    # 7. Analytics overview & spread endpoints
    overview = (await client.get("/api/v1/stats/overview")).json()
    assert overview["total_items"] >= 300
    assert len(overview["game_indices"]) == 2
    assert len(overview["rarity_stats"]) >= 3

    spreads = (await client.get("/api/v1/stats/spread?game=rust&limit=5")).json()
    assert len(spreads) == 5

    # 8. Case-insensitive Ukrainian Cyrillic search & Prime set related parts linking
    uk_lower = (await client.get("/api/v1/items?game=warframe&q=ґаусс")).json()
    uk_upper = (await client.get("/api/v1/items?game=warframe&q=ҐАУСС")).json()
    assert uk_lower["total"] >= 1
    assert uk_lower["total"] == uk_upper["total"]
    gauss_set = next(
        it for it in uk_lower["items"] if it["external_id"] == "gauss_prime_set"
    )
    gauss_card = (await client.get(f"/api/v1/items/{gauss_set['id']}")).json()
    assert len(gauss_card["related_parts"]) >= 3
    assert all(p["id"] != gauss_set["id"] for p in gauss_card["related_parts"])

    # 9. Warframes category contains zero mods
    wf_only = (
        await client.get("/api/v1/items?game=warframe&item_type=warframes&page_size=50")
    ).json()
    assert wf_only["total"] >= 1
    assert all(it["item_type"] == "warframes" for it in wf_only["items"])


@pytest.mark.integration
async def test_watchlist_crud_dedup_and_alerts_flow(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    client, _ = seeded_app
    headers = await auth_headers(client, "trader", "trader123!")

    items = (await client.get("/api/v1/items?game=rust&page_size=2")).json()["items"]
    item_id = items[1]["id"]
    market_id = (await client.get("/api/v1/markets?game=rust")).json()[0]["id"]

    # Create watch -> 201
    r1 = await client.post(
        "/api/v1/watch",
        json={
            "item_id": item_id,
            "market_id": market_id,
            "direction": "below",
            "threshold": "500.00",
            "cooldown_minutes": 30,
        },
        headers=headers,
    )
    assert r1.status_code == 201
    watch_id = r1.json()["id"]

    # Duplicate watch for same item+market -> 200 returning existing ID
    r2 = await client.post(
        "/api/v1/watch",
        json={
            "item_id": item_id,
            "market_id": market_id,
            "direction": "below",
            "threshold": "450.00",
        },
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == watch_id

    # Update threshold -> 200
    r_patch = await client.patch(
        f"/api/v1/watch/{watch_id}",
        json={"threshold": "420.50"},
        headers=headers,
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["threshold"] == "420.5000"

    # List alerts & mark read
    alerts = (await client.get("/api/v1/alerts?unread=true", headers=headers)).json()
    assert len(alerts) >= 1
    aid = alerts[0]["id"]
    r_read = await client.post(f"/api/v1/alerts/{aid}/read", headers=headers)
    assert r_read.status_code == 200
    assert r_read.json()["is_read"] is True

    # Delete watch -> 204
    assert (await client.delete(f"/api/v1/watch/{watch_id}", headers=headers)).status_code == 204
