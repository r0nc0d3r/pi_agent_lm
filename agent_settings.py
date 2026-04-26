"""Load `config.toml` (see `config.example.toml`). No broker hostnames or IPs in code."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef,import-not-found]


@dataclass(frozen=True)
class MqttConfig:
    broker_host: str
    port: int
    subscribe_pattern: str
    client_id: str
    publish_topic: str | None


@dataclass(frozen=True)
class WaterSensorConfig:
    pin_flow_bcm: int
    pin_leak_bcm: int
    pulse_k: float
    topic_flow: str
    topic_leak: str
    location: str
    flow_stabilize_s: float
    flow_stall_s: float
    data_interval_s: float


def default_config_path() -> Path:
    env = os.environ.get("PI_AGENT_LM_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path("config.toml")


def load_raw_config(path: Path | None = None) -> dict[str, Any]:
    p = path or default_config_path()
    if not p.is_file():
        raise FileNotFoundError(
            f"missing {p} — copy config.example.toml to config.toml and set broker hostname"
        )
    with p.open("rb") as f:
        data: dict[str, Any] = tomllib.load(f)
    return data


def parse_mqtt(raw: dict[str, Any]) -> MqttConfig:
    m = raw.get("mqtt")
    if not isinstance(m, dict):
        raise ValueError("config: missing [mqtt] table")
    host = m.get("broker_host")
    if not host or not str(host).strip():
        raise ValueError("config: mqtt.broker_host required (use hostname, not IP)")
    pub = m.get("publish_topic")
    pub_s = str(pub).strip() if pub is not None else ""
    return MqttConfig(
        broker_host=str(host).strip(),
        port=int(m.get("port", 1883)),
        subscribe_pattern=str(m.get("subscribe_pattern", "pi/sensor/#")),
        client_id=str(m.get("client_id", "pi-agent-lm")),
        publish_topic=pub_s or None,
    )


def parse_water_sensor(raw: dict[str, Any]) -> WaterSensorConfig:
    w = raw.get("water_sensor")
    if not isinstance(w, dict):
        raise ValueError("config: missing [water_sensor] table")
    return WaterSensorConfig(
        pin_flow_bcm=int(w["pin_flow_bcm"]),
        pin_leak_bcm=int(w["pin_leak_bcm"]),
        pulse_k=float(w.get("pulse_k", 7.5)),
        topic_flow=str(w.get("topic_flow", "pi/sensor/flow")),
        topic_leak=str(w.get("topic_leak", "pi/sensor/water")),
        location=str(w.get("location", "indoor")),
        flow_stabilize_s=float(w.get("flow_stabilize_s", 60.0)),
        flow_stall_s=float(w.get("flow_stall_s", 60.0)),
        data_interval_s=float(w.get("data_interval_s", 2.0)),
    )


def load_mqtt_config(path: Path | None = None) -> MqttConfig:
    return parse_mqtt(load_raw_config(path))


def load_water_sensor_bundle(path: Path | None = None) -> tuple[MqttConfig, WaterSensorConfig]:
    raw = load_raw_config(path)
    return parse_mqtt(raw), parse_water_sensor(raw)
