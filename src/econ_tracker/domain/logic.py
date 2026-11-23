"""Pure domain algorithms: normalization, classification, portfolio math, alerts, anomalies."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from econ_tracker.domain.enums import TradeSide, WatchDirection
from econ_tracker.domain.exceptions import DomainValidationError, InsufficientPositionError
from econ_tracker.domain.models import (
    AnomalyCheckResult,
    PositionState,
    RawMarketQuote,
    TradeRecord,
    ValidatedQuote,
)

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

_FOUR_PLACES = Decimal("0.0001")
_TWO_PLACES = Decimal("0.01")

def normalize_item_name(name: str) -> str:
    """Normalize an item name for deterministic cross-market matching."""
    cleaned = _WHITESPACE_RE.sub(" ", name.strip().lower())
    return _NON_ALNUM_RE.sub("_", cleaned).strip("_")

def convert_currency(amount: Decimal, rate_to_usd: Decimal) -> Decimal:
    """Convert original currency amount into USD with 4-decimal precision."""
    if amount <= Decimal("0"):
        raise DomainValidationError("Amount to convert must be strictly positive")
    if rate_to_usd <= Decimal("0"):
        raise DomainValidationError("Exchange rate must be strictly positive")
    return (amount * rate_to_usd).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)

def _matches_any(low: str, tokens: tuple[str, ...]) -> bool:
    for token in tokens:
        if len(token) <= 4 and " " not in token:
            if re.search(rf"\b{re.escape(token)}\b", low):
                return True
        elif token in low:
            return True
    return False

def classify_rust_item(name: str) -> tuple[str, str, str]:
    """Classify a Rust skin name into (category, subcategory, rarity)."""
    low = name.lower()

    tools_map: list[tuple[tuple[str, ...], str]] = [
        (("hatchet", "axe"), "hatchet"),
        (("pickaxe", "pick"), "pickaxe"),
        (("rock",), "rock"),
        (("hammer", "jackhammer"), "hammer"),
        (("satchel", "c4", "explosive"), "raiding"),
    ]
    for tokens, sub in tools_map:
        if _matches_any(low, tokens):
            return ("tools", sub, _infer_rust_rarity(low))

    deployables_map: list[tuple[tuple[str, ...], str]] = [
        (("garage door",), "garage_door"),
        (("armored door", "armoured door", "double door"), "armored_door"),
        (("sheet metal door", "metal door", "wooden door", "door"), "sheet_metal_door"),
        (("furnace",), "furnace"),
        (("large wood box", "large box", "wood box", "small box", "box", "chest"), "storage_box"),
        (("sleeping bag", "bag", "bed"), "sleeping_bag"),
        (("rug", "carpet", "table", "chair", "fridge", "vending", "locker"), "base_decor"),
    ]
    for tokens, sub in deployables_map:
        if _matches_any(low, tokens):
            return ("deployables", sub, _infer_rust_rarity(low))

    weapons_map: list[tuple[tuple[str, ...], str]] = [
        (("ak47", "ak-47", "assault rifle", "ar"), "ak47"),
        (("mp5",), "mp5"),
        (("lr-300", "lr300"), "lr300"),
        (("thompson",), "thompson"),
        (("sar", "semi-automatic rifle", "semi auto"), "sar"),
        (("bolt", "l96"), "sniper"),
        (("smg", "custom smg"), "custom_smg"),
        (("python", "revolver", "pistol", "m92", "sap", "eoka"), "pistol"),
        (("shotgun", "pump", "db", "double barrel", "spas"), "shotgun"),
        (("rocket", "launcher", "m249", "hmlmg"), "heavy"),
        (("bow", "crossbow"), "bow"),
        (("sword", "combat knife", "knife", "machete", "cleaver"), "melee"),
    ]
    for tokens, sub in weapons_map:
        if _matches_any(low, tokens):
            return ("weapons", sub, _infer_rust_rarity(low))

    clothing_map: list[tuple[tuple[str, ...], str]] = [
        (("hoodie",), "hoodie"),
        (("pants", "trousers", "shorts"), "pants"),
        (("facemask", "face mask", "mask"), "facemask"),
        (("chest plate", "chestplate", "plate"), "chestplate"),
        (("kilt", "roadsign", "road sign"), "kilt"),
        (("jacket", "poncho", "coat", "vest"), "jacket"),
        (("boots", "shoes"), "boots"),
        (("gloves",), "gloves"),
        (("helmet", "beanie", "hat", "cap", "balaclava", "boonie", "bandana"), "headgear"),
        (("t-shirt", "tshirt", "shirt", "longsleeve"), "shirt"),
        (("hazmat",), "hazmat"),
    ]
    for tokens, sub in clothing_map:
        if _matches_any(low, tokens):
            return ("clothing", sub, _infer_rust_rarity(low))

    return ("other", "misc", _infer_rust_rarity(low))

def _infer_rust_rarity(low_name: str) -> str:
    legendary_kw = ("big grin", "alien", "glory", "punishment", "tempered", "neon")
    rare_kw = ("gold", "dragon", "phantom", "blackout", "whiteout", "sinister")
    uncommon_kw = ("tactical", "carbon", "metal", "forest", "desert", "arctic")
    if any(k in low_name for k in legendary_kw):
        return "legendary"
    if any(k in low_name for k in rare_kw):
        return "rare"
    if any(k in low_name for k in uncommon_kw):
        return "uncommon"
    return "common"

def classify_warframe_item(tags: Sequence[str], name: str) -> tuple[str, str, str]:
    """Classify a Warframe Market item by tags into (category, subcategory, rarity)."""
    tag_set = {t.lower() for t in tags}
    low_name = name.lower()

    if "prime" in tag_set or "prime" in low_name:
        rarity = "prime"
    elif "legendary" in tag_set or "primed" in low_name:
        rarity = "legendary"
    elif "rare" in tag_set or "arcane_enhancement" in tag_set:
        rarity = "rare"
    elif "uncommon" in tag_set:
        rarity = "uncommon"
    else:
        rarity = "common"

    if "arcane_enhancement" in tag_set or "arcane" in tag_set:
        return ("arcanes", "arcane", rarity)
    if "mod" in tag_set:
        if "aura" in tag_set:
            return ("mods", "aura", rarity)
        if "stance" in tag_set:
            return ("mods", "stance", rarity)
        if "augment" in tag_set:
            return ("mods", "augment", rarity)
        return ("mods", "mod", rarity)
    if "relic" in tag_set:
        return ("relics", "void_relic", rarity)
    if "sentinel" in tag_set or "companion" in tag_set:
        return ("companions", "companion", rarity)
    if "warframe" in tag_set:
        sub = "prime_set" if "set" in tag_set else "blueprint"
        return ("warframes", sub, rarity)
    if "weapon" in tag_set or "primary" in tag_set or "secondary" in tag_set or "melee" in tag_set:
        if "primary" in tag_set:
            return ("weapons", "primary", rarity)
        if "secondary" in tag_set:
            return ("weapons", "secondary", rarity)
        if "melee" in tag_set:
            return ("weapons", "melee", rarity)
        return ("weapons", "weapon_set" if "set" in tag_set else "weapon_part", rarity)
    return ("other", "misc", rarity)

def validate_raw_quote(raw: RawMarketQuote, *, rate_to_usd: Decimal) -> ValidatedQuote:
    """Validate and convert a raw quote; raises DomainValidationError for bad records."""
    if not raw.name or not raw.name.strip():
        raise DomainValidationError("Missing item name")
    if not raw.external_id or not raw.external_id.strip():
        raise DomainValidationError("Missing external identifier")
    if raw.original_price is None or raw.original_price <= Decimal("0"):
        raise DomainValidationError(f"Non-positive price for {raw.name!r}: {raw.original_price}")
    if raw.volume is None or raw.volume < 0:
        raise DomainValidationError(f"Negative or missing volume for {raw.name!r}: {raw.volume}")

    normalized_name = normalize_item_name(raw.name)
    if not normalized_name:
        raise DomainValidationError(f"Item name normalizes to empty string: {raw.name!r}")

    normalized_price = convert_currency(raw.original_price, rate_to_usd)

    return ValidatedQuote(
        external_id=raw.external_id.strip(),
        name=raw.name.strip(),
        normalized_name=normalized_name,
        original_price=raw.original_price.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP),
        original_currency=raw.original_currency.upper().strip(),
        normalized_price=normalized_price,
        exchange_rate=rate_to_usd.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
        volume=raw.volume,
        collected_at=raw.collected_at,
        item_type=raw.item_type,
        subcategory=raw.subcategory,
        rarity=raw.rarity,
        icon_url=raw.icon_url,
        description=raw.description,
        released_at=raw.released_at,
    )

def should_create_snapshot(
    last_price: Decimal | None,
    last_volume: int | None,
    new_price: Decimal,
    new_volume: int,
) -> bool:
    """Create a new price snapshot only when price or offer volume actually changed."""
    if last_price is None or last_volume is None:
        return True
    return last_price != new_price or last_volume != new_volume

def recalculate_position(trades: Sequence[TradeRecord]) -> PositionState:
    """Replay trades in strict chronological order to compute position state.

    Supports backdated insertions and trade deletions transparently while enforcing
    the invariant that position quantity can never become negative.
    """
    ordered = sorted(trades, key=lambda t: (t.traded_at, t.trade_id))

    quantity = 0
    avg_cost = Decimal("0.0000")
    realized_pnl = Decimal("0.0000")

    for trade in ordered:
        if trade.side == TradeSide.BUY:
            total_cost = avg_cost * Decimal(quantity) + trade.price * Decimal(trade.quantity)
            quantity += trade.quantity
            avg_cost = (total_cost / Decimal(quantity)).quantize(
                _FOUR_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            if trade.quantity > quantity:
                raise InsufficientPositionError(
                    f"Cannot sell {trade.quantity} units at {trade.traded_at.isoformat()}: "
                    f"only {quantity} available"
                )
            pnl_delta = (trade.price - avg_cost) * Decimal(trade.quantity)
            realized_pnl = (realized_pnl + pnl_delta).quantize(
                _FOUR_PLACES, rounding=ROUND_HALF_UP
            )
            quantity -= trade.quantity
            if quantity == 0:
                avg_cost = Decimal("0.0000")

    return PositionState(
        quantity=quantity,
        avg_cost=avg_cost,
        realized_pnl=realized_pnl,
    )

def _threshold_condition_met(
    direction: WatchDirection,
    threshold: Decimal,
    price: Decimal,
) -> bool:
    if direction == WatchDirection.BELOW:
        return price <= threshold
    return price >= threshold

def should_trigger_watch(
    *,
    direction: WatchDirection,
    threshold: Decimal,
    current_price: Decimal,
    previous_price: Decimal | None,
    last_alert_at: datetime | None,
    cooldown_minutes: int,
    now: datetime,
) -> bool:
    """Return True only when price crosses the watch threshold outside the quiet cooldown."""
    currently_met = _threshold_condition_met(direction, threshold, current_price)
    if not currently_met:
        return False

    if previous_price is not None and _threshold_condition_met(
        direction, threshold, previous_price
    ):
        return False

    return not (
        last_alert_at is not None
        and cooldown_minutes > 0
        and now - last_alert_at < timedelta(minutes=cooldown_minutes)
    )

def evaluate_anomaly(
    *,
    current_price: Decimal,
    ma7_price: Decimal | None,
    threshold_pct: Decimal,
    has_open_event: bool,
    existing_max_deviation: Decimal | None = None,
) -> AnomalyCheckResult:
    """Evaluate 7-day moving average deviation to open, update, or auto-close anomalies."""
    if ma7_price is None or ma7_price <= Decimal("0"):
        return AnomalyCheckResult(
            action="none",
            deviation_pct=Decimal("0.00"),
            max_deviation_pct=existing_max_deviation or Decimal("0.00"),
        )

    deviation_pct = (((current_price - ma7_price) / ma7_price) * Decimal("100")).quantize(
        _TWO_PLACES, rounding=ROUND_HALF_UP
    )
    abs_dev = abs(deviation_pct)

    if abs_dev > threshold_pct:
        if has_open_event:
            prev_max = (
                existing_max_deviation
                if existing_max_deviation is not None
                else Decimal("0")
            )
            new_max = deviation_pct if abs_dev > abs(prev_max) else prev_max
            return AnomalyCheckResult(
                action="update",
                deviation_pct=deviation_pct,
                max_deviation_pct=new_max,
            )
        return AnomalyCheckResult(
            action="open",
            deviation_pct=deviation_pct,
            max_deviation_pct=deviation_pct,
        )

    if has_open_event:
        return AnomalyCheckResult(
            action="close",
            deviation_pct=deviation_pct,
            max_deviation_pct=existing_max_deviation or deviation_pct,
        )

    return AnomalyCheckResult(
        action="none",
        deviation_pct=deviation_pct,
        max_deviation_pct=Decimal("0.00"),
    )
