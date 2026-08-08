"""Deterministic fictional parties — sellers, importers, carriers.

Seeded from a ``random.Random`` so a case id always yields the same parties
(reproducible corpus). Names are assembled from generic tokens and are clearly
invented; the Armenian importer gets a well-formed 8-digit ՀՎՀՀ. None of this is
drawn from real data — the leak scanner enforces that separately.
"""

from __future__ import annotations

import random

from .ir import Party

_FOREIGN_STEMS = ["NOVA", "PRIME", "ORION", "HELIOS", "VERTEX", "AURA", "MERIDIAN", "CASPIAN",
                  "ATLAS", "LUMEN", "QUANTA", "ZENITH", "ARGO", "TITAN", "VESTA"]
_FOREIGN_KIND = ["CHEM", "TRADE", "INDUSTRIES", "MATERIALS", "GROUP", "EXPORT", "GMBH", "LTD"]
_FOREIGN_CITY = {
    "CN": "Shanghai", "DE": "Hamburg", "TR": "Istanbul", "ES": "Barcelona",
    "GB": "Manchester", "IT": "Milano", "FR": "Lyon", "NL": "Rotterdam",
}
_ARM_STEMS = ["ԱՐԱՐԱՏ", "ՍԵՎԱՆ", "ԱՐԱԳԱԾ", "ՎԱՆ", "ԳԱՐՆԻ", "ԼՈՌԻ", "ՇԻՐԱԿ", "ԿՈՏԱՅՔ", "ՄԱՍԻՍ"]
_ARM_KIND = ["ՇԻՆ", "ՏՐԵՅԴ", "ԳՐՈՒՊ", "ԻՄՊՈՐՏ", "ՊՐԵՍՏԻԺ", "ԿԱՊԻՏԱԼ"]
_CARRIERS = ["TransLine", "EuroCargo", "SilkRoad Logistics", "ContinentalFreight", "PanTrans"]


def foreign_seller(rng: random.Random, country: str) -> Party:
    name = f"{rng.choice(_FOREIGN_STEMS)} {rng.choice(_FOREIGN_KIND)}"
    city = _FOREIGN_CITY.get(country, "Port City")
    return Party(name=name, address=f"{rng.randint(1, 200)} Harbor Rd, {city}", country=country)


def armenian_importer(rng: random.Random) -> Party:
    name = f'"{rng.choice(_ARM_STEMS)} {rng.choice(_ARM_KIND)}" ՍՊԸ'
    tax_id = f"{rng.randint(10, 99)}{rng.randint(100000, 999999)}"  # 8-digit ՀՎՀՀ
    street = f"{rng.choice(('Աբովյան', 'Կոմիտաս', 'Բաղրամյան', 'Տիգրան Մեծ'))} {rng.randint(1, 120)}"
    return Party(name=name, address=f"{street}, Երևան", country="AM", tax_id=tax_id)


def carrier(rng: random.Random, country: str) -> Party:
    return Party(
        name=rng.choice(_CARRIERS),
        address=f"{rng.randint(1, 90)} Logistic Ave, {_FOREIGN_CITY.get(country, 'Port City')}",
        country=country,
    )
