from __future__ import annotations

import json

import pytest

import sensor_logic as sl


def test_sensor_from_topic_ok() -> None:
    assert sl.sensor_from_topic("pi/sensor/temp") == "temp"


def test_sensor_from_topic_nested() -> None:
    assert sl.sensor_from_topic("pi/sensor/water/leak") == "water/leak"
    assert sl.sensor_from_topic("prefix/pi/sensor/humidity") is None


def test_sensor_from_topic_bad() -> None:
    assert sl.sensor_from_topic("other/topic") is None


def test_decode_json() -> None:
    assert sl.decode_payload(b'{"value": 3.5, "unit": "C"}') == {"value": 3.5, "unit": "C"}


def test_decode_plain_number() -> None:
    assert sl.decode_payload(b"41.2") == {"value": 41.2}


def test_celsius_f() -> None:
    p = {"value": 104.0, "unit": "F"}
    assert sl.celsius_value(p) == pytest.approx(40.0, rel=1e-3)


def test_hard_rules_no_temp_threshold() -> None:
    assert sl.hard_rules("temp", {"value": 50.0, "unit": "C"}) == []


def test_hard_rules_water() -> None:
    assert "water_leak" in sl.hard_rules("water", {"leak": True})


def test_build_user_message() -> None:
    s = sl.build_user_message("pi/sensor/temp", "temp", {"value": 1}, ["x"])
    d = json.loads(s)
    assert d["sensor"] == "temp"
    assert d["rules_triggered"] == ["x"]
    assert "agent_context" in d
    assert "region" in d["agent_context"]
    assert "season_context" in d["agent_context"]
    assert "optional_payload_fields" in d["agent_context"]


def test_extract_json_object() -> None:
    out = sl.extract_json_object('noise {"a": 1} tail')
    assert out == {"a": 1}


def test_merge_output_temp_preserved() -> None:
    base = {
        "event": "heat_alert",
        "severity": "warning",
        "sensor": "temp",
        "reading": {"value": 41, "unit": "C", "raw": {}},
        "metadata": {"rules_triggered": [], "notes": "ok", "mqtt_topic": ""},
    }
    merged = sl.merge_output(base, "pi/sensor/temp", "temp", {"value": 41}, [])
    assert merged["severity"] == "warning"
    assert merged["event"] == "heat_alert"


def test_canonical_event_title_case() -> None:
    assert sl.canonical_event("Temperature Reading", []) == "temperature_reading"


def test_canonical_event_unknown() -> None:
    assert sl.canonical_event("Something Weird", []) == "general_reading"


def test_merge_output_canonicalizes_event() -> None:
    base = {
        "event": "not_a_real_event",
        "severity": "info",
        "sensor": "temp",
        "reading": {},
        "metadata": {"rules_triggered": [], "notes": ""},
    }
    merged = sl.merge_output(base, "t", "temp", {}, [])
    assert merged["event"] == "general_reading"


def test_merge_output_water_event() -> None:
    base = {
        "event": "general_reading",
        "severity": "info",
        "sensor": "water",
        "reading": {},
        "metadata": {"rules_triggered": [], "notes": ""},
    }
    merged = sl.merge_output(base, "pi/sensor/water", "water", {"leak": True}, ["water_leak"])
    assert merged["event"] == "water_leak"


def test_decode_empty() -> None:
    assert sl.decode_payload(b"") == {}


def test_decode_non_json_string() -> None:
    assert sl.decode_payload(b"not-json") == {"raw_text": "not-json"}


def test_celsius_kelvin() -> None:
    p = {"value": 313.15, "unit": "K"}
    assert sl.celsius_value(p) == pytest.approx(40.0, abs=0.01)


def test_hard_rules_humidity_agent_only() -> None:
    assert sl.hard_rules("humidity", {"value": 90}) == []


def test_hard_rules_flow() -> None:
    assert "flow_stalled" in sl.hard_rules("flow", {"value": 0.0})


def test_merge_flow_stalled_bumps_info() -> None:
    base = {
        "event": "reading",
        "severity": "info",
        "sensor": "flow",
        "reading": {},
        "metadata": {"rules_triggered": [], "notes": ""},
    }
    merged = sl.merge_output(base, "pi/sensor/flow", "flow", {"value": 0.0}, ["flow_stalled"])
    assert merged["severity"] == "warning"


def test_agent_region_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_REGION", "Rajasthan (arid NW)")
    monkeypatch.setenv("AGENT_TIMEZONE", "Asia/Kolkata")
    ctx = sl.get_agent_context()
    assert ctx["region"] == "Rajasthan (arid NW)"
    assert ctx["timezone"] == "Asia/Kolkata"


def test_merge_water_bumps_info() -> None:
    base = {
        "event": "reading",
        "severity": "info",
        "sensor": "water",
        "reading": {},
        "metadata": {"rules_triggered": [], "notes": ""},
    }
    merged = sl.merge_output(base, "pi/sensor/water", "water", {"leak": True}, ["water_leak"])
    assert merged["severity"] == "warning"


def test_extract_unbalanced() -> None:
    with pytest.raises(ValueError):
        sl.extract_json_object("{")
