"""Parse MQTT sensor topics/payloads, apply hard rules, build prompts, extract JSON."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Mapping, MutableMapping
from zoneinfo import ZoneInfo

# Topics like pi/sensor/temp, pi/sensor/humidity
TOPIC_PREFIX = "pi/sensor"

# Model must use one of these for "event" (post-merge normalization enforces).
CANONICAL_EVENTS = frozenset(
    {
        "temperature_reading",
        "heat_alert",
        "cold_alert",
        "humidity_reading",
        "water_leak",
        "flow_stalled",
        "general_reading",
    }
)

# Documented optional MQTT JSON keys — also passed to the model in agent_context.
PAYLOAD_FIELD_HINTS: dict[str, str] = {
    "location": "indoor | outdoor | mixed — indoor/AC spaces often need severity info unless distress signals exist",
    "outdoor_temp": "ambient °C if known (contrast with indoor reading)",
    "time_of_day": "morning | afternoon | evening | night",
    "weather": "free text or short code (clear, overcast, rain, …)",
    "heat_index": "°C or number if computed",
    "forecast": "short string if available",
    "occupant_vulnerable": "true if elderly, infant, medical heat/cold risk (raises justified concern)",
    "cooling_active": "true|false — AC/chiller known on",
    "heating_active": "true|false",
}


def sensor_from_topic(topic: str) -> str | None:
    """Return sensor id for pi/sensor/<name> or pi/sensor/a/b (joined as a/b)."""
    parts = topic.strip("/").split("/")
    if len(parts) < 3:
        return None
    if parts[0] != "pi" or parts[1] != "sensor":
        return None
    tail = "/".join(parts[2:])
    return tail or None


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def decode_payload(raw: bytes | str) -> dict[str, Any]:
    """Decode MQTT body: JSON object or plain number string."""
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace").strip()
    else:
        text = str(raw).strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return dict(data)
        return {"value": data}
    except json.JSONDecodeError:
        pass
    num = _to_float(text)
    if num is not None:
        return {"value": num}
    return {"raw_text": text}


def celsius_value(payload: Mapping[str, Any]) -> float | None:
    """Best-effort numeric reading in Celsius for temperature-like payloads."""
    unit = str(payload.get("unit") or payload.get("u") or "").upper()
    v = _to_float(payload.get("value"))
    if v is None:
        v = _to_float(payload.get("celsius"))
    if v is None:
        v = _to_float(payload.get("temp"))
    if v is None:
        return None
    if unit in ("F", "FAHRENHEIT"):
        return (v - 32.0) * (5.0 / 9.0)
    if unit in ("K", "KELVIN"):
        return v - 273.15
    return v


def _sensor_root(sensor: str) -> str:
    return sensor.lower().split("/")[0]


def _first_float(payload: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    """Like dict get-or chain but 0.0 stays valid (not skipped by `or`)."""
    for k in keys:
        if k in payload:
            return _to_float(payload[k])
    return None


def hard_rules(sensor: str, payload: Mapping[str, Any]) -> list[str]:
    """Objective flags only — temperature/humidity severity comes from the LLM + region/season context."""
    triggered: list[str] = []
    s = _sensor_root(sensor)
    if s == "water":
        leak = payload.get("leak") or payload.get("flooded")
        if leak is True or (isinstance(leak, (int, float)) and float(leak) != 0.0):
            triggered.append("water_leak")
    if s == "flow":
        rate = _first_float(payload, ("value", "rate", "lpm"))
        if rate is not None and rate <= 0.0:
            triggered.append("flow_stalled")
    return triggered


def _nw_india_season(month: int) -> str:
    """Rough season label for north-west India (local calendar month)."""
    if month in (12, 1, 2):
        return "winter — cool days, cold nights, fog possible"
    if month in (3, 4, 5):
        return "summer / pre-monsoon — dry heat building, heat waves possible"
    if month == 6:
        return "early monsoon transition — very hot pre-rain or first showers"
    if month in (7, 8, 9):
        return "monsoon — humid, cloudier, often cooler midday than peak summer"
    return "post-monsoon / autumn — clearer skies, easing humidity"


def get_agent_context() -> dict[str, Any]:
    """Region, local time, season hints for climate-aware severity (env overridable)."""
    region = os.environ.get("AGENT_REGION", "north-west India")
    tz_name = os.environ.get("AGENT_TIMEZONE", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
    except Exception:
        tz_name = "UTC"
        now = datetime.now(ZoneInfo("UTC"))
    month_idx = now.month
    return {
        "region": region,
        "timezone": tz_name,
        "local_iso_datetime": now.isoformat(timespec="seconds"),
        "season_context": _nw_india_season(month_idx),
        "optional_payload_fields": PAYLOAD_FIELD_HINTS,
        "guidance": (
            "Judge severity using region, season, and payload context. "
            "If location is indoor or cooling_active/heating_active implies climate-controlled space, prefer "
            "severity info for readings that are plausibly normal there — unless occupant_vulnerable is true, "
            "outdoor conditions are extreme, equipment failure is implied, or the payload flags distress. "
            "Use outdoor_temp vs indoor value to separate ambient harshness from cooled indoor comfort. "
            "When context is missing, infer cautiously and say so in notes. "
            "Keep metadata.notes to one or two short sentences."
        ),
    }


SYSTEM_PROMPT = """You are an edge IoT agent. Reply with exactly one JSON object (no markdown fences, no text before/after).

Required shape:
{
  "event": string,
  "severity": "info" | "warning" | "critical",
  "sensor": string,
  "reading": { "value": number | null, "unit": string | null, "raw": any },
  "metadata": {
    "mqtt_topic": string,
    "rules_triggered": string[],
    "notes": string
  }
}

Field "event" MUST be exactly one of these snake_case strings (no spaces, no Title Case):
  temperature_reading | heat_alert | cold_alert | humidity_reading | water_leak | flow_stalled | general_reading

Event choice:
- temperature_reading — routine temperature interpretation without strong alert.
- heat_alert — heat stress / excessive heat risk for the context.
- cold_alert — excessive cold risk for the context.
- humidity_reading — humidity-focused interpretation.
- water_leak — MUST use when rules_triggered contains "water_leak".
- flow_stalled — MUST use when rules_triggered contains "flow_stalled".
- general_reading — only if none of the above fit.

Rules:
- The user message includes agent_context (region, season, optional_payload_fields). Use region and season; use optional payload keys when present (see agent_context.optional_payload_fields).
- If rules_triggered includes "water_leak", set event water_leak and severity at least warning (critical if severe flooding).
- If rules_triggered includes "flow_stalled", set event flow_stalled and severity at least warning unless payload proves benign zero flow.
- Indoor / climate-controlled: prefer severity info when the reading is plausibly normal for AC/heating unless payload indicates vulnerable occupants, outdoor extremes, or system failure.
- metadata.notes: one or two short sentences max.
"""


def build_user_message(topic: str, sensor: str, payload: Mapping[str, Any], rules: list[str]) -> str:
    return json.dumps(
        {
            "mqtt_topic": topic,
            "sensor": sensor,
            "payload": dict(payload),
            "rules_triggered": rules,
            "agent_context": get_agent_context(),
        },
        ensure_ascii=False,
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull first top-level JSON object from model output."""
    t = text.strip()
    if not t:
        raise ValueError("empty model output")
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    for i in range(start, len(t)):
        ch = t[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(t[start : i + 1])
    raise ValueError("unbalanced JSON braces")


def canonical_event(raw: Any, hard_rules: list[str]) -> str:
    """Map model output to allowed event strings; honor objective rules first."""
    if "water_leak" in hard_rules:
        return "water_leak"
    if "flow_stalled" in hard_rules:
        return "flow_stalled"
    snake = "_".join(str(raw or "").strip().lower().split())
    if snake in CANONICAL_EVENTS:
        return snake
    return "general_reading"


def merge_output(
    model_obj: Mapping[str, Any],
    topic: str,
    sensor: str,
    payload: Mapping[str, Any],
    hard: list[str],
) -> dict[str, Any]:
    """Ensure metadata includes deterministic rules + topic; keep model fields when sane."""
    out: dict[str, Any] = dict(model_obj) if model_obj else {}
    out["sensor"] = sensor
    meta: MutableMapping[str, Any]
    if "metadata" in out and isinstance(out["metadata"], dict):
        meta = dict(out["metadata"])
    else:
        meta = {}
    rt = list(meta.get("rules_triggered") or [])
    for r in hard:
        if r not in rt:
            rt.append(r)
    meta["rules_triggered"] = rt
    meta["mqtt_topic"] = topic
    meta.setdefault("notes", "")
    out["metadata"] = dict(meta)
    out["event"] = canonical_event(out.get("event"), hard)
    out.setdefault("reading", {})
    if isinstance(out["reading"], dict):
        out["reading"].setdefault("raw", dict(payload))
    # Severity floor from objective hardware flags only (LLM decides temp/humidity)
    sev = str(out.get("severity") or "info").lower()
    if "water_leak" in rt and sev == "info":
        out["severity"] = "warning"
    if "flow_stalled" in rt and sev == "info":
        out["severity"] = "warning"
    return out
