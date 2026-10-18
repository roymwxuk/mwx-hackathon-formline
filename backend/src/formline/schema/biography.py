"""Synthetic public biographies, independent of match-generation randomness.

Also supplies missing fields in older synthetic league files without regenerating feeds.
Values are fictional assignments, never inferred from a player's name.
"""

import random
from datetime import date, timedelta

COUNTRIES = ("England", "Japan", "Italy", "Nigeria", "Germany", "Spain", "France",
             "Brazil", "Portugal", "Netherlands", "Scotland", "Wales")
PLACES = {
    "England": ("Bristol", "York"), "Japan": ("Osaka", "Sendai"),
    "Italy": ("Turin", "Bologna"), "Nigeria": ("Lagos", "Abuja"),
    "Germany": ("Hamburg", "Bremen"), "Spain": ("Seville", "Valencia"),
    "France": ("Lyon", "Nantes"), "Brazil": ("Recife", "Curitiba"),
    "Portugal": ("Braga", "Coimbra"), "Netherlands": ("Utrecht", "Eindhoven"),
    "Scotland": ("Dundee", "Aberdeen"), "Wales": ("Cardiff", "Swansea"),
}


def synthetic_biography(player_id: str) -> dict:
    rng = random.Random(f"formline:biography:v1:{player_id}")
    first, last = date(1990, 1, 1), date(2007, 12, 31)
    nationality = rng.choice(COUNTRIES)
    birthday = first + timedelta(days=rng.randrange((last - first).days + 1))
    # Separate stream preserves existing nationality/birthday assignments. Birthplace is
    # an explicit synthetic fact, not something the answering model infers from nationality.
    birthplace_rng = random.Random(f"formline:birthplace:v1:{player_id}")
    country = birthplace_rng.choice(COUNTRIES)
    city = birthplace_rng.choice(PLACES[country])
    return {"nationality": nationality, "date_of_birth": birthday,
            "birthplace": f"{city}, {country}"}
