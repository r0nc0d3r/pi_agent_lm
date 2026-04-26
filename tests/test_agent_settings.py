from __future__ import annotations

from pathlib import Path

import pytest

import agent_settings as ag


def _minimal_mqtt_toml() -> str:
    return """\
[mqtt]
broker_host = "broker.test.example"
port = 1883
subscribe_pattern = "pi/sensor/#"
client_id = "test-client"
publish_topic = ""

[water_sensor]
pin_flow_bcm = 17
pin_leak_bcm = 27
pulse_k = 7.5
topic_flow = "pi/sensor/flow"
topic_leak = "pi/sensor/water"
location = "indoor"
"""


def test_load_mqtt_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "cfg.toml"
    p.write_text(_minimal_mqtt_toml(), encoding="utf-8")
    monkeypatch.setenv("PI_AGENT_LM_CONFIG", str(p))
    m = ag.load_mqtt_config()
    assert m.broker_host == "broker.test.example"
    assert m.port == 1883
    assert m.subscribe_pattern == "pi/sensor/#"
    assert m.client_id == "test-client"
    assert m.publish_topic is None


def test_parse_mqtt_rejects_empty_host() -> None:
    with pytest.raises(ValueError, match="broker_host"):
        ag.parse_mqtt({"mqtt": {"broker_host": ""}})


def test_load_raw_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_AGENT_LM_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(FileNotFoundError):
        ag.load_raw_config()


def test_parse_mqtt_missing_table() -> None:
    with pytest.raises(ValueError, match="\\[mqtt\\]"):
        ag.parse_mqtt({})


def test_parse_water_sensor_missing_table() -> None:
    with pytest.raises(ValueError, match="\\[water_sensor\\]"):
        ag.parse_water_sensor({"mqtt": {"broker_host": "x"}})


def test_mqtt_publish_topic_string(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    t = _minimal_mqtt_toml().replace('publish_topic = ""', 'publish_topic = "pi/out/events"')
    p = tmp_path / "c.toml"
    p.write_text(t, encoding="utf-8")
    monkeypatch.setenv("PI_AGENT_LM_CONFIG", str(p))
    assert ag.load_mqtt_config().publish_topic == "pi/out/events"


def test_water_sensor_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "cfg.toml"
    p.write_text(_minimal_mqtt_toml(), encoding="utf-8")
    monkeypatch.setenv("PI_AGENT_LM_CONFIG", str(p))
    m, w = ag.load_water_sensor_bundle()
    assert w.pin_flow_bcm == 17
    assert w.topic_leak == "pi/sensor/water"
    assert m.broker_host == "broker.test.example"
