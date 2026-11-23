"""Integration tests for key portfolio trade operation, concurrency, idempotency, and RBAC."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from econ_tracker.api.deps import AppContainer
from tests.conftest import auth_headers


@pytest.mark.integration
async def test_healthz_openapi_and_correlation_id(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    client, _ = seeded_app
    resp = await client.get("/healthz", headers={"X-Request-ID": "trace-abc-123"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.headers["X-Request-ID"] == "trace-abc-123"

    openapi = await client.get("/openapi.json")
    assert openapi.status_code == 200
    assert "/api/v1/trades" in openapi.json()["paths"]

@pytest.mark.integration
async def test_trade_idempotency_oversell_backdated_delete_and_foreign_404(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    client, _ = seeded_app

    r1 = await client.post(
        "/api/v1/auth/register",
        json={"username": "alice_trader", "password": "password123"},
    )
    assert r1.status_code == 201
    h_alice = {"Authorization": f"Bearer {r1.json()['access_token']}"}

    r2 = await client.post(
        "/api/v1/auth/register",
        json={"username": "bob_trader", "password": "password123"},
    )
    assert r2.status_code == 201
    h_bob = {"Authorization": f"Bearer {r2.json()['access_token']}"}

    items = (await client.get("/api/v1/items?game=rust&page_size=1")).json()["items"]
    item_id = items[0]["id"]
    markets = (await client.get("/api/v1/markets?game=rust")).json()
    market_id = markets[0]["id"]

    t0 = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    payload = {
        "item_id": item_id,
        "market_id": market_id,
        "side": "buy",
        "qty": 2,
        "price": "100.00",
        "traded_at": (t0 + timedelta(days=2)).isoformat(),
        "idempotency_key": "idem-buy-1",
    }
    first = await client.post("/api/v1/trades", json=payload, headers=h_alice)
    assert first.status_code == 201
    trade_id = first.json()["id"]

    dup = await client.post("/api/v1/trades", json=payload, headers=h_alice)
    assert dup.status_code == 200
    assert dup.json()["id"] == trade_id

    oversell = await client.post(
        "/api/v1/trades",
        json={
            "item_id": item_id,
            "market_id": market_id,
            "side": "sell",
            "qty": 5,
            "price": "130.00",
            "traded_at": (t0 + timedelta(days=3)).isoformat(),
            "idempotency_key": "idem-oversell",
        },
        headers=h_alice,
    )
    assert oversell.status_code == 422
    assert oversell.headers["content-type"].startswith("application/problem+json")
    assert oversell.json()["type"] == "urn:econ-tracker:error:insufficient-position"

    backdated = await client.post(
        "/api/v1/trades",
        json={
            "item_id": item_id,
            "market_id": market_id,
            "side": "buy",
            "qty": 2,
            "price": "60.00",
            "traded_at": t0.isoformat(),
            "idempotency_key": "idem-backdated",
        },
        headers=h_alice,
    )
    assert backdated.status_code == 201
    backdated_id = backdated.json()["id"]

    sell_all = await client.post(
        "/api/v1/trades",
        json={
            "item_id": item_id,
            "market_id": market_id,
            "side": "sell",
            "qty": 4,
            "price": "110.00",
            "traded_at": (t0 + timedelta(days=4)).isoformat(),
            "idempotency_key": "idem-sell-all",
        },
        headers=h_alice,
    )
    assert sell_all.status_code == 201
    sell_id = sell_all.json()["id"]

    port = (await client.get("/api/v1/portfolio", headers=h_alice)).json()
    assert len(port["positions"]) == 1
    pos = port["positions"][0]
    assert pos["quantity"] == 0
    assert pos["realized_pnl"] == "120.00"

    assert (await client.get(f"/api/v1/trades/{trade_id}", headers=h_bob)).status_code == 404
    assert (
        await client.get(f"/api/v1/portfolio/positions/{pos['id']}", headers=h_bob)
    ).status_code == 404
    assert (await client.delete(f"/api/v1/trades/{trade_id}", headers=h_bob)).status_code == 404

    assert (await client.delete(f"/api/v1/trades/{sell_id}", headers=h_alice)).status_code == 204
    port_after = (await client.get("/api/v1/portfolio", headers=h_alice)).json()
    assert port_after["positions"][0]["quantity"] == 4
    assert port_after["positions"][0]["avg_cost"] == "80.0000"
    assert port_after["positions"][0]["realized_pnl"] == "0.00"

    assert (
        await client.delete(f"/api/v1/trades/{backdated_id}", headers=h_alice)
    ).status_code == 204
    port_final = (await client.get("/api/v1/portfolio", headers=h_alice)).json()
    assert port_final["positions"][0]["quantity"] == 2
    assert port_final["positions"][0]["avg_cost"] == "100.0000"

@pytest.mark.integration
async def test_concurrent_sales_only_one_succeeds(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    """Two simultaneous sells of qty=2 against qty=3 must yield exactly one 201 and one 422."""
    client, _ = seeded_app
    reg = await client.post(
        "/api/v1/auth/register",
        json={"username": "race_tester", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    item_id = (await client.get("/api/v1/items?game=rust&page_size=1")).json()["items"][0]["id"]
    market_id = (await client.get("/api/v1/markets?game=rust")).json()[0]["id"]
    now = datetime.now(UTC)

    buy = await client.post(
        "/api/v1/trades",
        json={
            "item_id": item_id,
            "market_id": market_id,
            "side": "buy",
            "qty": 3,
            "price": "50.00",
            "traded_at": (now - timedelta(hours=2)).isoformat(),
            "idempotency_key": "race-buy",
        },
        headers=headers,
    )
    assert buy.status_code == 201

    res1, res2 = await asyncio.gather(
        client.post(
            "/api/v1/trades",
            json={
                "item_id": item_id,
                "market_id": market_id,
                "side": "sell",
                "qty": 2,
                "price": "60.00",
                "traded_at": now.isoformat(),
                "idempotency_key": "race-sell-1",
            },
            headers=headers,
        ),
        client.post(
            "/api/v1/trades",
            json={
                "item_id": item_id,
                "market_id": market_id,
                "side": "sell",
                "qty": 2,
                "price": "60.00",
                "traded_at": now.isoformat(),
                "idempotency_key": "race-sell-2",
            },
            headers=headers,
        ),
    )
    codes = sorted([res1.status_code, res2.status_code])
    assert codes == [201, 422]

    port = (await client.get("/api/v1/portfolio", headers=headers)).json()
    assert port["positions"][0]["quantity"] == 1

@pytest.mark.integration
async def test_rbac_enforcement_for_analyst_and_admin(
    seeded_app: tuple[httpx.AsyncClient, AppContainer],
) -> None:
    client, _ = seeded_app
    h_user = await auth_headers(client, "trader", "trader123!")
    h_analyst = await auth_headers(client, "analyst", "analyst123!")
    h_admin = await auth_headers(client, "admin", "admin123!")

    open_anoms = (await client.get("/api/v1/anomalies?status=open")).json()
    assert len(open_anoms) >= 1
    anom_id = open_anoms[0]["id"]

    r_forbid = await client.post(
        f"/api/v1/anomalies/{anom_id}/close",
        json={"comment": "Should fail"},
        headers=h_user,
    )
    assert r_forbid.status_code == 403

    r_close = await client.post(
        f"/api/v1/anomalies/{anom_id}/close",
        json={"comment": "Confirmed patch hype spike."},
        headers=h_analyst,
    )
    assert r_close.status_code == 200
    assert r_close.json()["status"] == "closed"
    assert r_close.json()["comment"] == "Confirmed patch hype spike."

    assert (await client.post("/api/v1/collect/run", headers=h_user)).status_code == 403
    r_col = await client.post("/api/v1/collect/run", headers=h_admin)
    assert r_col.status_code == 200
    runs = r_col.json()
    assert len(runs) == 4

    by_code = {r["market_code"]: r for r in runs}
    assert by_code["wf_ps"]["status"] == "failed"
    assert "outage" in (by_code["wf_ps"]["error_message"] or "")
    assert by_code["wf_pc"]["status"] == "partial"
    assert by_code["wf_pc"]["accepted_count"] == 1
    assert by_code["wf_pc"]["rejected_count"] == 1
    assert by_code["skinport_rust"]["status"] == "success"
    assert by_code["rust_tm"]["status"] == "success"

    status_resp = await client.get("/api/v1/admin/collection/status", headers=h_admin)
    assert status_resp.status_code == 200
    assert len(status_resp.json()) == 4

    g_resp = await client.post(
        "/api/v1/admin/games",
        json={"name": "Counter-Strike 2", "code": "cs2", "is_active": True},
        headers=h_admin,
    )
    assert g_resp.status_code == 201
    new_game_id = g_resp.json()["id"]

    g_patch = await client.patch(
        f"/api/v1/admin/games/{new_game_id}",
        json={"is_active": False},
        headers=h_admin,
    )
    assert g_patch.status_code == 200 and g_patch.json()["is_active"] is False

    m_bad = await client.post(
        "/api/v1/admin/markets",
        json={
            "game_id": new_game_id,
            "name": "Fast Market",
            "code": "fast_m",
            "base_url": "https://fast.test",
            "currency": "USD",
            "schedule_minutes": 5,
        },
        headers=h_admin,
    )
    assert m_bad.status_code == 422

    m_ok = await client.post(
        "/api/v1/admin/markets",
        json={
            "game_id": new_game_id,
            "name": "CS2 Market",
            "code": "cs2_market",
            "base_url": "https://cs2.test",
            "currency": "EUR",
            "schedule_minutes": 30,
        },
        headers=h_admin,
    )
    assert m_ok.status_code == 201
    m_patch = await client.patch(
        f"/api/v1/admin/markets/{m_ok.json()['id']}",
        json={"schedule_minutes": 60},
        headers=h_admin,
    )
    assert m_patch.status_code == 200 and m_patch.json()["schedule_minutes"] == 60
