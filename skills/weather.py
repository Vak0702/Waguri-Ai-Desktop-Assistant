"""
weather.py — Weather reports using free, keyless APIs:
  - Open-Meteo (https://open-meteo.com) for forecasts and city geocoding —
    no API key, no account, no rate-limit surprises for personal use.
  - ip-api.com for approximate current location via IP address — only ever
    called after the user has explicitly said yes, once.

Privacy design: saying "weather in <city>" never touches location at all —
it's a direct place lookup. Only an implicit "what's the weather" (no city
named) needs your current location, and that only happens after you've
explicitly granted permission. Consent is remembered in memory/settings.json
so you're only asked once; you can revoke it anytime (handled in brain.py).
"""

from __future__ import annotations

import json
import os

import requests

import config

WEATHER_CODES = {  # WMO weather interpretation codes -> human description
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "a thunderstorm", 96: "a thunderstorm with slight hail", 99: "a thunderstorm with heavy hail",
}


def _load_settings() -> dict:
    if not os.path.exists(config.SETTINGS_PATH):
        return {}
    with open(config.SETTINGS_PATH, "r") as f:
        return json.load(f)


def _save_settings(data: dict):
    os.makedirs(os.path.dirname(config.SETTINGS_PATH), exist_ok=True)
    with open(config.SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_location_consent() -> bool | None:
    """None = never asked yet, True = allowed, False = declined."""
    return _load_settings().get("location_consent")


def set_location_consent(allowed: bool):
    data = _load_settings()
    data["location_consent"] = allowed
    _save_settings(data)


def _describe_code(code: int) -> str:
    return WEATHER_CODES.get(code, "unknown conditions")


def _format_weather(current: dict, place_name: str) -> str:
    temp = current.get("temperature")
    wind = current.get("windspeed")
    desc = _describe_code(current.get("weathercode", -1))
    return (f"It's currently {temp:.0f} degrees Celsius and {desc} in {place_name}, "
            f"with wind around {wind:.0f} kilometers per hour.")


def get_weather_for_coords(lat: float, lon: float, place_name: str) -> str:
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon, "current_weather": "true"},
            timeout=8,
        )
        resp.raise_for_status()
        return _format_weather(resp.json()["current_weather"], place_name)
    except Exception as e:
        return f"I couldn't get the weather right now — {e}"


def get_weather_for_city(city: str) -> str:
    """Direct place lookup — no location permission needed since the user
    named the place explicitly."""
    try:
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=8,
        )
        geo_resp.raise_for_status()
        results = geo_resp.json().get("results")
        if not results:
            return f"I couldn't find a place called {city}."
        place = results[0]
        return get_weather_for_coords(place["latitude"], place["longitude"], place.get("name", city))
    except Exception as e:
        return f"I couldn't look up the weather for {city} — {e}"


def get_weather_for_current_location() -> str:
    """Only called after explicit consent — uses approximate IP-based
    geolocation, not GPS (desktops generally don't have GPS anyway)."""
    try:
        ip_resp = requests.get("http://ip-api.com/json/", timeout=8)
        ip_resp.raise_for_status()
        ip_data = ip_resp.json()
        if ip_data.get("status") != "success":
            return "I couldn't determine your location right now."
        place_name = ip_data.get("city", "your area")
        return get_weather_for_coords(ip_data["lat"], ip_data["lon"], place_name)
    except Exception as e:
        return f"I couldn't determine your location right now — {e}"