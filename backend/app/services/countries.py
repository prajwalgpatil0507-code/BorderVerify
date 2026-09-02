"""ICAO country / nationality code mapping (subset for the prototype).

Provides human readable names for the 3-letter codes found in MRZ zones and
passport photo pages.  This is display data only - it does not affect the
verification logic.
"""
from __future__ import annotations

COUNTRY_NAMES: dict[str, str] = {
    "UTO": "Utopia (Demo)",
    "DMO": "Demonland (Demo)",
    "IND": "India",
    "USA": "United States of America",
    "GBR": "United Kingdom",
    "FRA": "France",
    "DEU": "Germany",
    "CAN": "Canada",
    "AUS": "Australia",
    "CHN": "China",
    "JPN": "Japan",
    "BGD": "Bangladesh",
    "PAK": "Pakistan",
    "NPL": "Nepal",
    "LKA": "Sri Lanka",
    "NGA": "Nigeria",
    "KEN": "Kenya",
    "ZAF": "South Africa",
    "BRA": "Brazil",
    "MEX": "Mexico",
    "ARE": "United Arab Emirates",
    "SAU": "Saudi Arabia",
    "SGP": "Singapore",
    "MYS": "Malaysia",
    "IDN": "Indonesia",
    "RUS": "Russia",
    "ITA": "Italy",
    "ESP": "Spain",
}


def country_name(code: str) -> str:
    if not code:
        return ""
    return COUNTRY_NAMES.get(code.upper(), code)


def sex_name(code: str) -> str:
    return {"M": "Male", "F": "Female", "<": "Unknown"}.get(code, code or "Unknown")
