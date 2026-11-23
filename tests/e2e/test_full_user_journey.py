"""End-to-end user journey test covering registration, catalog, watch, collection, and portfolio."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from econ_tracker.api.deps import AppContainer
from tests.conftest import auth_headers


@pytest.mark.e2e
async def test_complete_end_to_end_user_journey(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    """Walk through the full product workflow from registration to realized portfolio PnL."""
    client, _ = seeded_app

    games = (await client.get("/api/v1/games")).json()
    assert any(g["code"] == "warframe" for g in games)

    search = (
        await client.get("/api/v1/items?game=warframe&q=Gauss%20Prime%20Set")
    ).json()
    assert search["total"] >= 1
    gauss = next(
        it for it in search["items"] if (it.get("name_en") or it["name"]) == "Gauss Prime Set"
    )
    assert gauss["description"] is not None

    detail = (await client.get(f"/api/v1/items/{gauss['id']}")).json()
    wf_pc_market_id = next(m["market_id"] for m in detail["markets"] if m["market_code"] == "wf_pc")

    csv_resp = await client.get(f"/api/v1/items/{gauss['id']}/prices?step=day&format=csv")
    assert csv_resp.status_code == 200 and len(csv_resp.text.splitlines()) >= 5

    reg = await client.post(
        "/api/v1/auth/register",
        json={"username": "e2e_tenno", "password": "strongpassword1"},
    )
    assert reg.status_code == 201
    user_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    watch_resp = await client.post(
        "/api/v1/watch",
        json={
            "item_id": gauss["id"],
            "market_id": wf_pc_market_id,
            "direction": "below",
            "threshold": "2.50",
            "cooldown_minutes": 60,
        },
        headers=user_headers,
    )
    assert watch_resp.status_code == 201

    admin_headers = await auth_headers(client, "admin", "admin123!")
    col_resp = await client.post(
        "/api/v1/collect/run",
        json={"market_id": wf_pc_market_id},
        headers=admin_headers,
    )
    assert col_resp.status_code == 200

    unread_alerts = (await client.get("/api/v1/alerts?unread=true", headers=user_headers)).json()
    assert len(unread_alerts) == 1
    msg = unread_alerts[0]["message"]
    assert "Gauss" in msg or "Ґаусс" in msg

    now = datetime.now(UTC)
    t_buy = await client.post(
        "/api/v1/trades",
        json={
            "item_id": gauss["id"],
            "market_id": wf_pc_market_id,
            "side": "buy",
            "qty": 10,
            "price": "2.00",
            "traded_at": (now - timedelta(hours=2)).isoformat(),
            "idempotency_key": "e2e-buy-1",
        },
        headers=user_headers,
    )
    assert t_buy.status_code == 201

    t_sell = await client.post(
        "/api/v1/trades",
        json={
            "item_id": gauss["id"],
            "market_id": wf_pc_market_id,
            "side": "sell",
            "qty": 4,
            "price": "3.00",
            "traded_at": now.isoformat(),
            "idempotency_key": "e2e-sell-1",
        },
        headers=user_headers,
    )
    assert t_sell.status_code == 201

    portfolio = (await client.get("/api/v1/portfolio", headers=user_headers)).json()
    assert portfolio["realized_pnl"] == "4.00"
    assert portfolio["invested"] == "12.00"
    assert len(portfolio["positions"]) == 1
    assert portfolio["positions"][0]["quantity"] == 6
