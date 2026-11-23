"""Idempotent database seeder producing 320+ real Warframe & Rust items and 30 days of history."""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import bcrypt
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from econ_tracker.domain.enums import AnomalyStatus, CollectionStatus, TradeSide, UserRole
from econ_tracker.domain.logic import (
    convert_currency,
    normalize_item_name,
    recalculate_position,
)
from econ_tracker.domain.models import TradeRecord
from econ_tracker.logging_config import get_logger
from econ_tracker.storage.orm_models import (
    AlertORM,
    AnomalyEventORM,
    CollectionRunORM,
    GameORM,
    ItemORM,
    MarketORM,
    PositionORM,
    PriceSnapshotORM,
    TradeORM,
    UserORM,
    WatchItemORM,
)

logger = get_logger(__name__)

_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class _SeedItemSpec:
    name: str
    item_type: str
    subcategory: str
    rarity: str
    base_usd: float
    base_vol: int
    description: str | None
    days_since_release: int
    anomaly_spike: float = 0.0  # non-zero triggers a realistic recent anomaly


def _build_rust_catalog() -> list[_SeedItemSpec]:
    """Generate 180 authentic Rust skins spanning all major Rust Labs categories."""
    specs: list[_SeedItemSpec] = [
        # Iconic flagship Rust skins
        _SeedItemSpec("Big Grin", "clothing", "facemask", "legendary", 695.0, 9, None, 3120),
        _SeedItemSpec("Alien Red", "weapons", "ak47", "legendary", 128.0, 24, None, 2940, 0.34),
        _SeedItemSpec("Glory AK47", "weapons", "ak47", "legendary", 214.0, 15, None, 2890),
        _SeedItemSpec("Punishment Mask", "clothing", "facemask", "legendary", 412.0, 7, None, 3050),
        _SeedItemSpec("Tempered Mask", "clothing", "facemask", "legendary", 19.5, 62, None, 2400),
        _SeedItemSpec("Tempered MP5", "weapons", "mp5", "legendary", 17.8, 54, None, 2210, -0.28),
        _SeedItemSpec("Blackout Hoodie", "clothing", "hoodie", "rare", 11.4, 88, None, 1980),
        _SeedItemSpec("Whiteout Hoodie", "clothing", "hoodie", "rare", 14.9, 71, None, 1920),
        _SeedItemSpec("Forest Raiders Hoodie", "clothing", "hoodie", "uncommon", 9.6, 95, None, 1540),
        _SeedItemSpec("Desert Raiders Hoodie", "clothing", "hoodie", "uncommon", 8.8, 102, None, 1500),
        _SeedItemSpec("Blackout Pants", "clothing", "pants", "rare", 10.2, 92, None, 1980),
        _SeedItemSpec("Whiteout Pants", "clothing", "pants", "rare", 13.7, 68, None, 1920),
        _SeedItemSpec("Blackout Chest Plate", "clothing", "chestplate", "rare", 16.5, 60, None, 1850),
        _SeedItemSpec("Whiteout Chest Plate", "clothing", "chestplate", "rare", 21.0, 44, None, 1800),
        _SeedItemSpec("Blackout Kilt", "clothing", "kilt", "rare", 12.1, 77, None, 1850),
        _SeedItemSpec("No Mercy AK47", "weapons", "ak47", "rare", 18.2, 74, None, 1620),
        _SeedItemSpec("From Hell AK47", "weapons", "ak47", "rare", 15.6, 65, None, 1740),
        _SeedItemSpec("Glory SAR", "weapons", "sar", "legendary", 38.4, 31, None, 2310),
        _SeedItemSpec("Polymer LR-300", "weapons", "lr300", "uncommon", 4.9, 118, None, 1320),
        _SeedItemSpec("Neon Storage Box", "deployables", "storage_box", "legendary", 14.2, 85, None, 1490),
        _SeedItemSpec("Dragon Furnace", "deployables", "furnace", "rare", 11.8, 72, None, 1680, 0.31),
        _SeedItemSpec("Volcanic Furnace", "deployables", "furnace", "rare", 8.9, 94, None, 1790),
        _SeedItemSpec("Neon Garage Door", "deployables", "garage_door", "legendary", 16.4, 80, None, 1410),
        _SeedItemSpec("Molten Visage Garage Door", "deployables", "garage_door", "rare", 9.2, 110, None, 1340),
        _SeedItemSpec("Sinister Sheet Metal Door", "deployables", "sheet_metal_door", "rare", 7.4, 126, None, 1520),
        _SeedItemSpec("Factory Armored Door", "deployables", "armored_door", "uncommon", 6.1, 90, None, 1210),
        _SeedItemSpec("Lumberjack Hatchet", "tools", "hatchet", "uncommon", 4.4, 135, None, 1450),
        _SeedItemSpec("Molten Pickaxe", "tools", "pickaxe", "rare", 6.8, 108, None, 1380),
        _SeedItemSpec("Obsidian Rock", "tools", "rock", "uncommon", 3.5, 160, None, 1600),
        _SeedItemSpec("Tactical Hammer", "tools", "hammer", "common", 2.9, 144, None, 1150),
    ]

    # Systematic expansion across Rust collections x subcategories to reach 180 real-style skins
    collections: list[tuple[str, str, float]] = [
        ("Blackout", "rare", 1.8),
        ("Whiteout", "rare", 2.0),
        ("Forest Raiders", "uncommon", 1.35),
        ("Desert Raiders", "uncommon", 1.25),
        ("Arctic", "uncommon", 1.15),
        ("No Mercy", "rare", 1.9),
        ("Tempered", "legendary", 2.8),
        ("Neon", "legendary", 2.5),
        ("Doodle", "common", 0.75),
        ("Cobalt", "uncommon", 1.05),
        ("Phantom", "rare", 1.65),
        ("Dragon", "rare", 1.75),
        ("Carbon", "uncommon", 1.1),
        ("Sinister", "rare", 1.55),
        ("Tactical", "uncommon", 1.0),
    ]

    templates: list[tuple[str, str, str, float, int]] = [
        ("Hoodie", "clothing", "hoodie", 5.2, 85),
        ("Pants", "clothing", "pants", 4.6, 90),
        ("Metal Facemask", "clothing", "facemask", 8.5, 58),
        ("Metal Chest Plate", "clothing", "chestplate", 9.1, 52),
        ("Roadsign Kilt", "clothing", "kilt", 4.1, 76),
        ("Jacket", "clothing", "jacket", 3.8, 82),
        ("Tactical Gloves", "clothing", "gloves", 3.2, 104),
        ("Boots", "clothing", "boots", 2.9, 112),
        ("AK-47", "weapons", "ak47", 10.4, 64),
        ("MP5", "weapons", "mp5", 6.2, 78),
        ("LR-300", "weapons", "lr300", 5.8, 72),
        ("Thompson", "weapons", "thompson", 5.1, 88),
        ("SAR", "weapons", "sar", 4.9, 92),
        ("Bolt Action Rifle", "weapons", "sniper", 7.3, 48),
        ("Pump Shotgun", "weapons", "shotgun", 3.6, 98),
        ("Python Revolver", "weapons", "pistol", 3.1, 105),
        ("Furnace", "deployables", "furnace", 4.3, 86),
        ("Garage Door", "deployables", "garage_door", 5.5, 96),
        ("Sheet Metal Door", "deployables", "sheet_metal_door", 3.4, 120),
        ("Large Wood Box", "deployables", "storage_box", 4.8, 110),
        ("Sleeping Bag", "deployables", "sleeping_bag", 2.7, 130),
        ("Hatchet", "tools", "hatchet", 2.8, 115),
        ("Pickaxe", "tools", "pickaxe", 3.0, 112),
    ]

    existing = {normalize_item_name(s.name) for s in specs}
    idx = 0
    for col_name, rarity, mult in collections:
        for base_label, cat, sub, base_price, base_vol in templates:
            if len(specs) >= 180:
                break
            full_name = f"{col_name} {base_label}"
            norm = normalize_item_name(full_name)
            if norm in existing:
                continue
            existing.add(norm)
            idx += 1
            price = round(base_price * mult * (0.85 + (idx % 7) * 0.06), 2)
            vol = max(8, int(base_vol * (0.7 + (idx % 5) * 0.15)))
            days_old = 240 + (idx * 17) % 1900
            specs.append(
                _SeedItemSpec(
                    name=full_name,
                    item_type=cat,
                    subcategory=sub,
                    rarity=rarity,
                    base_usd=price,
                    base_vol=vol,
                    description=None,
                    days_since_release=days_old,
                )
            )
        if len(specs) >= 180:
            break

    return specs


def _build_warframe_catalog() -> list[_SeedItemSpec]:
    """Generate 140 authentic Warframe Market items with rich descriptions & categories."""
    prime_frames = [
        ("Gauss Prime", 48, "High-velocity kinetic Warframe engineered for relentless Mach Rush speed and thermal overload."),
        ("Wisp Prime", 54, "Ethereal dimensional Warframe deploying Reservoirs that boost vitality, haste, and shock defense."),
        ("Revenant Prime", 62, "Eidolon-infused Warframe protected by Mesmer Skin charges and sweeping Danse Macabre beams."),
        ("Saryn Prime", 105, "Bio-alchemical specialist spreading escalating corrosive Spores and lethal Miasma clouds."),
        ("Mesa Prime", 96, "Gunslinger Warframe unleashing auto-targeting Peacemaker Regulator pistols with devastating precision."),
        ("Volt Prime", 118, "Electromagnetic Warframe providing squad Speed, defensive Electric Shields, and room-wide Discharge."),
        ("Octavia Prime", 74, "Acoustic tactician powered by the Mandachord, granting invisibility and scaling Mallet damage."),
        ("Protea Prime", 68, "Temporal engineer deploying Blaze Artillery turrets, Dispensary supplies, and Temporal Anchor."),
        ("Sevagoth Prime", 58, "Void-touched helmsman commanding an exalted Shadow form and sowing death-mark debuffs."),
        ("Xaku Prime", 79, "Amalgam Warframe stripping armor with The Vast Untime and turning enemy weapons against them."),
        ("Titania Prime", 84, "Razorwing pixie Warframe capable of high-speed aerial combat with dual Dex Pixia pistols."),
        ("Khora Prime", 71, "Beastmaster accompanied by Venari, ensnaring crowds inside her Strangledome whipcage."),
        ("Nezha Prime", 92, "Agile warding Warframe sliding at high speed behind blazing Fire Walker trails and Warding Halo."),
        ("Hildryn Prime", 64, "Shield-powered juggernaut draining enemy defenses with Pillage to fuel Aegis Storm."),
        ("Baruuk Prime", 69, "Pacifist monk channeling restrained fury into Desert Wind shockwaves."),
        ("Harrow Prime", 56, "Void priest converting headshots and shields into squad energy and guaranteed critical strikes."),
        ("Garuda Prime", 78, "Crimson warrior sacrificing health for energy and impaling foes with Seeking Talons."),
        ("Nidus Prime", 88, "Infested Warframe building Mutation stacks to achieve near-immortality and massive Parasitic Link power."),
        ("Ember Prime", 124, "Pyrokinetic Warframe raining Inferno meteors while managing her Immolation heat gauge."),
        ("Frost Prime", 112, "Cryogenic defender fortifying objectives inside reinforced Snow Globes."),
        ("Rhino Prime", 132, "Heavy assault Warframe shrugging off incoming damage with Iron Skin and amplifying squad Roar."),
        ("Nova Prime", 126, "Antimatter manipulator accelerating or slowing entire battlefields with Molecular Prime."),
        ("Mirage Prime", 82, "Illusionist multiplying weapon output through Hall of Mirrors and Eclipse light amplification."),
        ("Nekros Prime", 115, "Necromancer increasing loot drop rolls via Desecrate and raising Shadows of the Dead."),
        ("Chroma Prime", 86, "Elemental dragon adapting Vex Armor into massive weapon damage and armor multipliers."),
        ("Valkyr Prime", 94, "Berserker Warframe entering invulnerable Hysteria rage with exalted energy claws."),
        ("Ivara Prime", 76, "Stealth huntress stalking corridors in Prowl and firing guided Artemis Bow volleys."),
        ("Inaros Prime", 90, "Desert guardian boasting colossal health pools and regenerating through Scarab Armor."),
        ("Ash Prime", 128, "Shadow assassin teleporting into lethal Blade Storm finishers and Smoke Screen stealth."),
        ("Loki Prime", 142, "Master trickster controlling engagements with Radial Disarm, Decoy, and extended Invisibility."),
    ]

    weapons: list[tuple[str, str, str, int, str]] = [
        ("Glaive Prime Set", "melee", "prime", 195, "Vaulted Orokin throwing disc delivering forced slash procs on heavy detonation."),
        ("Nikana Prime Set", "melee", "prime", 118, "Masterwork Orokin katana offering high critical multiplier and fast sweeping combos."),
        ("Kronen Prime Set", "melee", "prime", 135, "Twin sovereign tonfas renowned for relentless slash status and high attack speed."),
        ("Redeemer Prime Set", "melee", "prime", 82, "Heavy gunblade capable of firing concentrated shotgun blasts during melee combos."),
        ("Gram Prime Set", "melee", "prime", 74, "Colossal heavy blade combining high status chance with crushing critical strikes."),
        ("Guandao Prime Set", "melee", "prime", 68, "Long-reach Orokin polearm built for sweeping critical cleaves across wide crowds."),
        ("Orthos Prime Set", "melee", "prime", 34, "Lightweight dual-bladed polearm prized for rapid attacks and wide status coverage."),
        ("Reaper Prime Set", "melee", "prime", 96, "Classic vaulted Orokin scythe specializing in heavy-attack slash bleeds."),
        ("Venka Prime Set", "melee", "prime", 88, "Prime claw weapons capable of scaling melee combo counter up to 13x."),
        ("Acceltra Prime Set", "primary", "prime", 52, "Rapid-fire micro-missile rifle designed for mobile crowd clearing at mid-range."),
        ("Fulmin Prime Set", "primary", "prime", 46, "Rechargeable electric rifle toggling between silent shotgun pulses and automatic fire."),
        ("Ignis Wraith Blueprint", "primary", "rare", 14, "High-capacity flamethrower projecting continuous heat streams across hallways."),
        ("Rubico Prime Set", "primary", "prime", 98, "High-magnification sniper rifle favored for Eidolon hunts and single-target crits."),
        ("Vectis Prime Set", "primary", "prime", 114, "Vaulted bolt-action Orokin sniper rifle with rapid reload cadence."),
        ("Braton Prime Set", "primary", "prime", 22, "Evergreen automatic rifle upgraded with Incarnon Genesis adaptability."),
        ("Burston Prime Set", "primary", "prime", 26, "Burst-fire rifle transformed into a top-tier endgame powerhouse via Incarnon adapter."),
        ("Latron Prime Set", "primary", "prime", 58, "Precision semi-automatic rifle prized for armor-stripping Incarnon projectiles."),
        ("Phantasma Prime Set", "primary", "prime", 42, "Beam shotgun saturating targets with devastating heat and radiation status procs."),
        ("Cedo Prime Set", "primary", "prime", 64, "Status-priming shotgun launching ricocheting elemental glaives before full-auto blasts."),
        ("Trumna Prime Set", "primary", "prime", 61, "Heavy Entrati-inspired rifle charging an explosive secondary bounce grenade."),
        ("Epitaph Prime Set", "secondary", "prime", 44, "Wrist-mounted sidearm priming cold/blast AoE or firing pinpoint crit bolts."),
        ("Akarius Prime Set", "secondary", "prime", 49, "Dual homing rocket pistols paired with Gauss Prime for explosive mobility."),
        ("Lex Prime Set", "secondary", "prime", 18, "High-caliber Orokin sidearm with iconic heavy punch-through and Incarnon form."),
        ("Pyrana Prime Set", "secondary", "prime", 66, "Automatic pocket shotgun summoning a spectral twin pistol after rapid kills."),
        ("Knell Prime Set", "secondary", "prime", 48, "Precision scoped pistol gaining infinite ammo and crit bonuses on headshots."),
        ("Laetum Blueprint", "secondary", "rare", 28, "Zariman Incarnon pistol evolving into rapid-fire explosive rounds on headshots."),
        ("Dual Toxocyst Blueprint", "secondary", "uncommon", 24, "Infested dual pistols entering frenzied toxin overdrive after landing headshots."),
        ("Nautilus Prime Set", "weapons", "prime", 55, "Railjack sentinel grouping enemies tightly with Cordon and auto-repairing hulls."),
        ("Verglas Prime Set", "primary", "prime", 47, "High-status cryogenic sentinel beam rifle capable of melting steel-path foes."),
        ("Okina Prime Set", "melee", "prime", 41, "Dual Orokin sai daggers enhanced by pausing combo timers and Incarnon daggers."),
    ]

    mods: list[tuple[str, str, str, int, str]] = [
        ("Primed Continuity", "mod", "legendary", 88, "Baro Ki'Teer Primed mod extending Warframe Ability Duration by up to +55%."),
        ("Primed Flow", "mod", "legendary", 92, "Primed Warframe mod expanding maximum Energy capacity by up to +185%."),
        ("Primed Pressure Point", "mod", "legendary", 95, "Primed melee mod amplifying base melee weapon damage by +165%."),
        ("Primed Reach", "mod", "legendary", 84, "Primed melee mod extending blade sweep range by +3.0 meters."),
        ("Primed Target Cracker", "mod", "legendary", 90, "Primed pistol mod increasing Critical Damage multiplier by +110%."),
        ("Primed Pistol Gambit", "mod", "legendary", 86, "Primed pistol mod raising secondary Critical Chance by +187%."),
        ("Primed Cryo Rounds", "mod", "legendary", 78, "Primed rifle mod adding +165% Cold damage for Viral combinations."),
        ("Primed Fever Strike", "mod", "legendary", 82, "Primed melee mod adding +165% Toxin damage for Corrosive or Viral builds."),
        ("Condition Overload", "mod", "rare", 16, "Melee mod granting +80% base damage per unique status effect on the target."),
        ("Adaptation", "mod", "rare", 19, "Arbitration defensive mod building up to 90% resistance against received damage types."),
        ("Rolling Guard", "mod", "rare", 21, "Arbitration survival mod granting 3s invulnerability and status cleanse on dodge."),
        ("Blood Rush", "mod", "uncommon", 14, "Deimos melee mod scaling Critical Chance by +40% per Combo Multiplier tier."),
        ("Weeping Wounds", "mod", "uncommon", 18, "Deimos melee mod scaling Status Chance by +40% per Combo Multiplier tier."),
        ("Galvanized Chamber", "mod", "rare", 22, "Arbitration rifle mod stacking huge Multishot bonuses on consecutive kills."),
        ("Galvanized Diffusion", "mod", "rare", 20, "Arbitration pistol mod providing up to +230% total Multishot at full stacks."),
        ("Galvanized Aptitude", "mod", "rare", 24, "Rifle mod boosting Status Chance and direct damage per status type on target."),
        ("Brief Respite", "aura", "uncommon", 28, "Silver Grove Aura converting 150% of spent Energy into instant Shields."),
        ("Growing Power", "aura", "rare", 44, "Silver Grove Aura granting +25% Ability Strength for 6s after applying status."),
        ("Corrosive Projection", "aura", "uncommon", 15, "Squad Aura reducing enemy armor across the mission by -18%."),
        ("Steel Charge", "aura", "uncommon", 16, "High-capacity Aura boosting squad Melee Damage by +60%."),
        ("Blind Rage", "mod", "rare", 24, "Orokin Vault corrupted mod trading Ability Efficiency for +99% Ability Strength."),
        ("Transient Fortitude", "mod", "rare", 22, "Corrupted Warframe mod granting +55% Ability Strength at the cost of Duration."),
        ("Overextended", "mod", "rare", 25, "Corrupted Warframe mod boosting Ability Range by +90% while reducing Strength."),
        ("Fleeting Expertise", "mod", "rare", 23, "Corrupted Warframe mod granting +60% Ability Efficiency for reduced Duration."),
        ("Narrow Minded", "mod", "rare", 24, "Corrupted Warframe mod expanding Ability Duration by +99% for reduced Range."),
        ("Tempo Royale", "stance", "rare", 32, "Fluid heavy-blade stance mod combining sweeping slams and high mobility."),
        ("Sovereign Outcast", "stance", "uncommon", 12, "Rapid tonfa stance mod delivering high-multiplier slash procs."),
        ("Wise Razor", "stance", "uncommon", 14, "Two-handed Nikana stance mod built around sweeping arc strikes."),
        ("Pilfering Strangledome", "augment", "rare", 16, "Khora Augment granting enemies caught in Strangledome 65% extra loot chance."),
        ("Fused Reservoir", "augment", "rare", 15, "Wisp Augment allowing all three Motes to be placed simultaneously in one cast."),
    ]

    arcanes: list[tuple[str, str, int, str]] = [
        ("Arcane Energize (R5)", "legendary", 435, "Legendary Eidolon Arcane granting a 60% chance to replenish 150 squad Energy on orb pickup."),
        ("Arcane Grace (R5)", "legendary", 265, "Legendary Arcane triggering 6% health regeneration per second when taking health damage."),
        ("Arcane Barrier (R5)", "legendary", 175, "Legendary Arcane instantly restoring full Shields on hit with a 6% trigger chance."),
        ("Arcane Avenger (R5)", "rare", 210, "Rare Arcane adding a flat +45% Critical Chance for 12s upon taking damage."),
        ("Arcane Aegis (R5)", "rare", 245, "Rare defensive Arcane granting continuous 30% Shield Recharge even under fire."),
        ("Arcane Fury (R5)", "rare", 138, "Rare melee Arcane boosting Melee Damage by +180% after landing critical hits."),
        ("Arcane Velocity (R5)", "uncommon", 82, "Uncommon Arcane increasing Pistol Fire Rate by +120% on critical hits."),
        ("Arcane Strike (R5)", "uncommon", 64, "Uncommon Arcane boosting Melee Attack Speed by +60% on hit."),
        ("Molt Augmented (R5)", "rare", 76, "Zariman Arcane permanently stacking up to +60% Ability Strength over 250 kills."),
        ("Molt Efficiency (R5)", "rare", 54, "Zariman Arcane providing +36% Ability Duration while Shields remain active."),
        ("Cascadia Flare (R5)", "rare", 48, "Zariman secondary Arcane stacking up to +480% damage on Heat status procs."),
        ("Melee Influence (R5)", "rare", 62, "Sanctum melee Arcane spreading elemental status effects across 20m on Electricity proc."),
        ("Melee Duplicate (R5)", "legendary", 285, "Legendary Netracell Arcane causing yellow melee crits to strike twice."),
        ("Melee Crescendo (R5)", "legendary", 190, "Legendary Arcane granting permanent Initial Combo for every finisher kill."),
        ("Secondary Encumber (R5)", "rare", 115, "Mirror Defense Arcane adding random extra status procs on every status trigger."),
        ("Primary Frostbite (R5)", "rare", 44, "Lua Arcane stacking Critical Damage and Multishot on Cold status effects."),
        ("Primary Merciless (R5)", "rare", 24, "Steel Path Arcane stacking +360% Primary Damage and +30% Reload Speed on kills."),
        ("Primary Deadhead (R5)", "rare", 22, "Steel Path Arcane rewarding precision headshot kills with +360% damage and recoil control."),
        ("Secondary Merciless (R5)", "rare", 21, "Steel Path sidearm Arcane boosting secondary weapon damage up to +360%."),
        ("Eternal Eradicate (R5)", "rare", 38, "Zariman Amp Arcane adding +60% Operator Amp damage on ability cast."),
    ]

    specs: list[_SeedItemSpec] = []
    plt_to_usd = 0.04999

    # 30 Prime Sets + 30 Prime Blueprints = 60 warframe items
    for i, (wf_name, plt_price, desc) in enumerate(prime_frames):
        spike = 0.36 if i == 0 else (-0.27 if i == 4 else 0.0)
        specs.append(
            _SeedItemSpec(
                name=f"{wf_name} Set",
                item_type="warframes",
                subcategory="prime_set",
                rarity="prime",
                base_usd=round(plt_price * plt_to_usd, 4),
                base_vol=38 + (i * 7) % 75,
                description=desc,
                days_since_release=180 + i * 70,
                anomaly_spike=spike,
            )
        )
        specs.append(
            _SeedItemSpec(
                name=f"{wf_name} Blueprint",
                item_type="warframes",
                subcategory="blueprint",
                rarity="prime",
                base_usd=round(max(8, int(plt_price * 0.32)) * plt_to_usd, 4),
                base_vol=55 + (i * 11) % 90,
                description=f"Main blueprint component for crafting {wf_name}. {desc}",
                days_since_release=180 + i * 70,
            )
        )

    for i, (w_name, sub, rarity, plt_price, desc) in enumerate(weapons):
        specs.append(
            _SeedItemSpec(
                name=w_name,
                item_type="weapons",
                subcategory=sub,
                rarity=rarity,
                base_usd=round(plt_price * plt_to_usd, 4),
                base_vol=30 + (i * 9) % 80,
                description=desc,
                days_since_release=220 + i * 55,
                anomaly_spike=0.29 if i == 0 else 0.0,
            )
        )

    for i, (m_name, sub, rarity, plt_price, desc) in enumerate(mods):
        specs.append(
            _SeedItemSpec(
                name=m_name,
                item_type="mods",
                subcategory=sub,
                rarity=rarity,
                base_usd=round(plt_price * plt_to_usd, 4),
                base_vol=45 + (i * 13) % 110,
                description=desc,
                days_since_release=400 + i * 48,
            )
        )

    for i, (a_name, rarity, plt_price, desc) in enumerate(arcanes):
        specs.append(
            _SeedItemSpec(
                name=a_name,
                item_type="arcanes",
                subcategory="arcane",
                rarity=rarity,
                base_usd=round(plt_price * plt_to_usd, 4),
                base_vol=14 + (i * 5) % 45,
                description=desc,
                days_since_release=300 + i * 60,
            )
        )

    return specs


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def seed_database(
    session: AsyncSession,
    *,
    if_empty: bool = False,
    days: int = 30,
    eur_to_usd: Decimal = Decimal("1.080000"),
    plt_to_usd: Decimal = Decimal("0.049990"),
) -> dict[str, int]:
    """Populate games, markets, users, 320+ items, 30 days of snapshots, portfolio, and alerts."""
    existing_items = await session.scalar(select(func.count(ItemORM.id)))
    if if_empty and existing_items and existing_items > 0:
        logger.info("seed_skipped_non_empty", existing_items=existing_items)
        return {"items": int(existing_items), "snapshots": 0, "skipped": 1}

    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)

    # 1. Games
    games_map: dict[str, GameORM] = {}
    for code, name in (("warframe", "Warframe"), ("rust", "Rust")):
        game = await session.scalar(select(GameORM).where(GameORM.code == code))
        if game is None:
            game = GameORM(name=name, code=code, is_active=True)
            session.add(game)
            await session.flush()
        games_map[code] = game

    # 2. Markets (2 per game for genuine M:N cross-market spread & multi-currency)
    market_defs = [
        (
            "wf_pc",
            "warframe",
            "Warframe.market (PC)",
            "https://api.warframe.market/v2",
            "PLT",
            Decimal("0.00"),
            15,
        ),
        (
            "wf_ps",
            "warframe",
            "Warframe.market (PS)",
            "https://api.warframe.market/v2",
            "PLT",
            Decimal("0.00"),
            15,
        ),
        (
            "skinport_rust",
            "rust",
            "Skinport (Rust EUR)",
            "https://api.skinport.com/v1/items",
            "EUR",
            Decimal("12.00"),
            15,
        ),
        (
            "rust_tm",
            "rust",
            "Rust.tm (USD)",
            "https://rust.tm/api/v2/prices/USD.json",
            "USD",
            Decimal("5.00"),
            15,
        ),
    ]
    markets_map: dict[str, MarketORM] = {}
    for code, game_code, name, url, cur, fee, sched in market_defs:
        m = await session.scalar(select(MarketORM).where(MarketORM.code == code))
        if m is None:
            m = MarketORM(
                game_id=games_map[game_code].id,
                name=name,
                code=code,
                base_url=url,
                currency=cur,
                fee_pct=fee,
                schedule_minutes=sched,
                is_active=True,
                last_collected_at=now,
            )
            session.add(m)
            await session.flush()
        markets_map[code] = m

    # 3. Demo Users for all roles
    users_map: dict[str, UserORM] = {}
    for uname, pwd, role in (
        ("admin", "admin123!", UserRole.ADMIN.value),
        ("analyst", "analyst123!", UserRole.ANALYST.value),
        ("trader", "trader123!", UserRole.USER.value),
    ):
        u = await session.scalar(select(UserORM).where(UserORM.username == uname))
        if u is None:
            u = UserORM(username=uname, password_hash=_hash_password(pwd), role=role)
            session.add(u)
            await session.flush()
        users_map[uname] = u

    # 4. Items + 30 days of historical PriceSnapshots across 2 markets per item
    catalog_by_game: list[tuple[str, list[_SeedItemSpec], tuple[MarketORM, MarketORM]]] = [
        ("warframe", _build_warframe_catalog(), (markets_map["wf_pc"], markets_map["wf_ps"])),
        ("rust", _build_rust_catalog(), (markets_map["skinport_rust"], markets_map["rust_tm"])),
    ]

    snapshot_rows: list[dict[str, Any]] = []
    created_items: list[ItemORM] = []
    anomalies_to_create: list[AnomalyEventORM] = []

    for game_code, specs, (market_a, market_b) in catalog_by_game:
        game = games_map[game_code]
        for spec in specs:
            norm = normalize_item_name(spec.name)
            existing = await session.scalar(
                select(ItemORM).where(
                    ItemORM.game_id == game.id,
                    ItemORM.normalized_name == norm,
                )
            )
            if existing is not None:
                continue

            rng_seed = int(hashlib.sha256(f"{game_code}:{norm}".encode()).hexdigest()[:8], 16)
            rng = random.Random(rng_seed)

            item = ItemORM(
                game_id=game.id,
                name=spec.name,
                normalized_name=norm,
                item_type=spec.item_type,
                subcategory=spec.subcategory,
                rarity=spec.rarity,
                external_id=norm if game_code == "warframe" else spec.name,
                is_available=True,
                description=spec.description,
                released_at=now - timedelta(days=spec.days_since_release),
            )
            session.add(item)
            created_items.append(item)

        await session.flush()

        # Generate 30 days of realistic correlated price trajectories on both markets
        item_lookup = {
            it.normalized_name: it
            for it in created_items
            if it.game_id == game.id
        }

        for spec in specs:
            norm = normalize_item_name(spec.name)
            item_or_none = item_lookup.get(norm)
            if item_or_none is None:
                continue

            rng_seed = int(hashlib.sha256(f"hist:{game_code}:{norm}".encode()).hexdigest()[:8], 16)
            rng = random.Random(rng_seed)
            drift = rng.uniform(-0.0025, 0.0035)
            phase = rng.uniform(0, math.tau)
            market_b_premium = rng.uniform(1.03, 1.19)

            daily_usd_a: list[Decimal] = []
            daily_usd_b: list[Decimal] = []
            last_vol_a = spec.base_vol
            last_vol_b = max(2, int(spec.base_vol * rng.uniform(0.45, 0.85)))

            for day_offset in range(days - 1, -1, -1):
                ts = now - timedelta(days=day_offset)
                t_idx = days - 1 - day_offset
                wave = 1.0 + 0.055 * math.sin(t_idx * 0.42 + phase) + drift * t_idx
                noise_a = rng.uniform(0.97, 1.03)
                noise_b = rng.uniform(0.97, 1.03)

                usd_a = max(0.15, spec.base_usd * wave * noise_a)
                if day_offset == 0 and spec.anomaly_spike != 0.0:
                    usd_a = max(0.15, usd_a * (1.0 + spec.anomaly_spike))

                usd_b = max(0.15, usd_a * market_b_premium * noise_b)
                if day_offset == 0 and spec.anomaly_spike != 0.0:
                    # Keep market B near baseline to create an interesting spread as well
                    usd_b = max(0.15, spec.base_usd * wave * market_b_premium)

                vol_a = max(1, int(spec.base_vol * rng.uniform(0.7, 1.35)))
                vol_b = max(1, int(spec.base_vol * rng.uniform(0.35, 0.85)))
                last_vol_a, last_vol_b = vol_a, vol_b

                for market, usd_val, vol in (
                    (market_a, usd_a, vol_a),
                    (market_b, usd_b, vol_b),
                ):
                    if market.currency == "PLT":
                        orig_price = Decimal(
                            max(1, round(usd_val / float(plt_to_usd)))
                        ).quantize(_Q4)
                        rate = plt_to_usd
                        norm_price = convert_currency(orig_price, rate)
                    elif market.currency == "EUR":
                        orig_price = Decimal(str(round(usd_val / float(eur_to_usd), 2))).quantize(
                            _Q4
                        )
                        rate = eur_to_usd
                        norm_price = convert_currency(orig_price, rate)
                    else:
                        orig_price = Decimal(str(round(usd_val, 2))).quantize(_Q4)
                        rate = Decimal("1.000000")
                        norm_price = orig_price

                    if market.id == market_a.id:
                        daily_usd_a.append(norm_price)
                    else:
                        daily_usd_b.append(norm_price)

                    snapshot_rows.append(
                        {
                            "item_id": item_or_none.id,
                            "market_id": market.id,
                            "original_price": orig_price,
                            "original_currency": market.currency,
                            "normalized_price": norm_price,
                            "exchange_rate": rate,
                            "volume": vol,
                            "collected_at": ts,
                            "last_checked_at": ts,
                        }
                    )

            # Precompute Item metrics (MA-7, min/max, spread, 24h/7d change)
            last_a = daily_usd_a[-1]
            last_b = daily_usd_b[-1]
            prev_7 = daily_usd_a[-8:-1] if len(daily_usd_a) >= 8 else daily_usd_a[:-1]
            ma7 = (
                (sum(prev_7, Decimal("0")) / Decimal(len(prev_7))).quantize(
                    _Q4, rounding=ROUND_HALF_UP
                )
                if prev_7
                else last_a
            )
            min_p = min(last_a, last_b)
            max_p = max(last_a, last_b)
            spread = (
                (((max_p - min_p) / min_p) * Decimal("100")).quantize(_Q2, rounding=ROUND_HALF_UP)
                if min_p > Decimal("0")
                else Decimal("0.00")
            )
            p_24h = daily_usd_a[-2] if len(daily_usd_a) >= 2 else last_a
            p_7d = daily_usd_a[-8] if len(daily_usd_a) >= 8 else daily_usd_a[0]
            chg_24h = (((last_a - p_24h) / p_24h) * Decimal("100")).quantize(
                _Q2, rounding=ROUND_HALF_UP
            )
            chg_7d = (((last_a - p_7d) / p_7d) * Decimal("100")).quantize(
                _Q2, rounding=ROUND_HALF_UP
            )

            item_or_none.ma7_price = ma7
            item_or_none.latest_min_price = min_p
            item_or_none.latest_max_price = max_p
            item_or_none.latest_total_volume = last_vol_a + last_vol_b
            item_or_none.spread_pct = spread
            item_or_none.price_change_24h_pct = chg_24h
            item_or_none.price_change_7d_pct = chg_7d

            if spec.anomaly_spike != 0.0 and ma7 > Decimal("0"):
                dev = (((last_a - ma7) / ma7) * Decimal("100")).quantize(
                    _Q2, rounding=ROUND_HALF_UP
                )
                if abs(dev) > Decimal("20.00"):
                    anomalies_to_create.append(
                        AnomalyEventORM(
                            item_id=item_or_none.id,
                            market_id=market_a.id,
                            status=AnomalyStatus.OPEN.value,
                            ma7_price=ma7,
                            trigger_price=last_a,
                            deviation_pct=dev,
                            max_deviation_pct=dev,
                            opened_at=now - timedelta(hours=3),
                        )
                    )

    # Batch-insert snapshots in chunks of 1000 for speed on both Postgres & SQLite
    chunk_size = 1000
    for i in range(0, len(snapshot_rows), chunk_size):
        await session.execute(insert(PriceSnapshotORM), snapshot_rows[i : i + chunk_size])

    session.add_all(anomalies_to_create)

    # 5. Seed sample closed anomaly, collection runs, portfolio trades, and watch/alerts
    if created_items:
        sample_wf = next((it for it in created_items if it.game_id == games_map["warframe"].id), created_items[0])
        sample_rust = next((it for it in created_items if it.game_id == games_map["rust"].id), created_items[-1])

        session.add(
            AnomalyEventORM(
                item_id=sample_rust.id,
                market_id=markets_map["skinport_rust"].id,
                status=AnomalyStatus.CLOSED.value,
                ma7_price=sample_rust.ma7_price or Decimal("10.0000"),
                trigger_price=(sample_rust.ma7_price or Decimal("10.0000")) * Decimal("1.26"),
                deviation_pct=Decimal("26.00"),
                max_deviation_pct=Decimal("28.40"),
                opened_at=now - timedelta(days=4),
                closed_at=now - timedelta(days=3, hours=14),
                closed_by_user_id=users_map["analyst"].id,
                comment="Verified Twitch Drops event spike; price normalized after drop ended.",
            )
        )

        # Sample collection runs for Admin status page
        for m in markets_map.values():
            session.add(
                CollectionRunORM(
                    market_id=m.id,
                    status=CollectionStatus.SUCCESS.value,
                    started_at=now - timedelta(minutes=2),
                    finished_at=now - timedelta(minutes=1, seconds=48),
                    accepted_count=140 if m.game_id == games_map["warframe"].id else 180,
                    rejected_count=2,
                    new_snapshots_count=140 if m.game_id == games_map["warframe"].id else 180,
                    error_message=None,
                )
            )

        # Seed demo portfolio for 'trader'
        trader = users_map["trader"]
        demo_trades_spec = [
            (sample_rust, markets_map["skinport_rust"], TradeSide.BUY, 2, Decimal("105.0000"), now - timedelta(days=12), "seed-trade-1"),
            (sample_rust, markets_map["rust_tm"], TradeSide.SELL, 1, Decimal("124.5000"), now - timedelta(days=4), "seed-trade-2"),
            (sample_wf, markets_map["wf_pc"], TradeSide.BUY, 5, Decimal("2.1000"), now - timedelta(days=9), "seed-trade-3"),
        ]
        by_item: dict[int, list[TradeRecord]] = {}
        for idx_t, (it, mkt, side, qty, price, t_at, idem) in enumerate(demo_trades_spec, start=1):
            tr = TradeORM(
                user_id=trader.id,
                item_id=it.id,
                market_id=mkt.id,
                side=side.value,
                quantity=qty,
                price=price,
                traded_at=t_at,
                idempotency_key=idem,
            )
            session.add(tr)
            by_item.setdefault(it.id, []).append(
                TradeRecord(
                    trade_id=idx_t,
                    side=side,
                    quantity=qty,
                    price=price,
                    traded_at=t_at,
                )
            )
        for item_id, records in by_item.items():
            pos_state = recalculate_position(records)
            session.add(
                PositionORM(
                    user_id=trader.id,
                    item_id=item_id,
                    quantity=pos_state.quantity,
                    avg_cost=pos_state.avg_cost,
                    realized_pnl=pos_state.realized_pnl,
                )
            )

        # Seed WatchItem + Alert for 'trader'
        watch = WatchItemORM(
            user_id=trader.id,
            item_id=sample_wf.id,
            market_id=markets_map["wf_pc"].id,
            direction="below",
            threshold=(sample_wf.latest_min_price or Decimal("3.0000")) + Decimal("0.5000"),
            cooldown_minutes=60,
            last_alert_at=now - timedelta(hours=2),
        )
        session.add(watch)
        await session.flush()

        latest_snap = await session.scalar(
            select(PriceSnapshotORM)
            .where(
                PriceSnapshotORM.item_id == sample_wf.id,
                PriceSnapshotORM.market_id == markets_map["wf_pc"].id,
            )
            .order_by(PriceSnapshotORM.collected_at.desc())
            .limit(1)
        )
        if latest_snap is not None:
            session.add(
                AlertORM(
                    watch_item_id=watch.id,
                    user_id=trader.id,
                    snapshot_id=latest_snap.id,
                    triggered_price=latest_snap.normalized_price,
                    message=(
                        f"{sample_wf.name} crossed below "
                        f"${watch.threshold:.2f} (now ${latest_snap.normalized_price:.2f})"
                    ),
                    is_read=False,
                )
            )

    await session.commit()
    logger.info(
        "seed_completed",
        items=len(created_items),
        snapshots=len(snapshot_rows),
        anomalies=len(anomalies_to_create) + 1,
    )
    return {
        "items": len(created_items),
        "snapshots": len(snapshot_rows),
        "anomalies": len(anomalies_to_create) + 1,
    }
