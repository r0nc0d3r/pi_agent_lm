"""MQTT subscriber + LiteRT-LM (Gemma 4 E2B) local inference for Pi sensor topics."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import paho.mqtt.client as mqtt

import agent_settings as cfg
import sensor_logic as sl

try:
    import litert_lm
except ImportError as e:  # pragma: no cover - env without wheel
    litert_lm = None  # type: ignore[assignment]
    _LITERT_IMPORT_ERROR = e
else:
    _LITERT_IMPORT_ERROR = None

LOG = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma-4-E2B-it.litertlm"


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def run_inference(
    engine: Any,
    *,
    topic: str,
    sensor: str,
    payload: dict[str, Any],
    rules: list[str],
) -> dict[str, Any]:
    """One-shot conversation: structured JSON from Gemma."""
    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": sl.SYSTEM_PROMPT}],
        },
    ]
    user_text = sl.build_user_message(topic, sensor, payload, rules)
    with engine.create_conversation(messages=messages) as conversation:
        response = conversation.send_message(user_text)
    text = response["content"][0]["text"]
    parsed = sl.extract_json_object(text)
    return sl.merge_output(parsed, topic, sensor, payload, rules)


def make_on_message(engine: Any, publish_topic: str | None):
    def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic or ""
        sensor = sl.sensor_from_topic(topic)
        if not sensor:
            LOG.warning("skip topic (not %s/<name>): %s", sl.TOPIC_PREFIX, topic)
            return
        payload = sl.decode_payload(msg.payload)
        rules = sl.hard_rules(sensor, payload)
        try:
            result = run_inference(
                engine,
                topic=topic,
                sensor=sensor,
                payload=payload,
                rules=rules,
            )
        except Exception as e:
            LOG.exception("inference failed for %s", topic)
            result = {
                "event": "inference_error",
                "severity": "warning",
                "sensor": sensor,
                "reading": {"value": None, "unit": None, "raw": payload},
                "metadata": {
                    "mqtt_topic": topic,
                    "rules_triggered": rules,
                    "notes": str(e),
                },
            }
        line = json.dumps(result, ensure_ascii=False)
        print(line, flush=True)
        if publish_topic:
            qos = _env_int("AGENT_MQTT_PUBLISH_QOS", 1)
            client.publish(publish_topic, line.encode("utf-8"), qos=qos)

    return on_message


def build_engine(model_path: str) -> Any:
    if litert_lm is None:
        raise RuntimeError(
            "litert_lm not importable; install with: uv pip install litert-lm-nightly"
        ) from _LITERT_IMPORT_ERROR
    litert_lm.set_min_log_severity(litert_lm.LogSeverity.ERROR)
    backend = getattr(litert_lm.Backend, "CPU", None)
    kwargs: dict[str, Any] = {}
    if backend is not None:
        kwargs["backend"] = backend
    cache_dir = os.environ.get("LITERT_LM_CACHE_DIR")
    if cache_dir:
        kwargs["cache_dir"] = cache_dir
    return litert_lm.Engine(model_path, **kwargs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    model_path = _env("LITERT_LM_MODEL", DEFAULT_MODEL)
    if not os.path.isfile(model_path):
        LOG.error("model file missing: %s", model_path)
        LOG.error(
            "see https://github.com/google-ai-edge/LiteRT-LM — e.g. "
            "uv tool run litert-lm run "
            "--from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm "
            '%s --prompt="What is the capital of France?"',
            DEFAULT_MODEL,
        )
        LOG.error(
            "or fetch into cwd: uv run python scripts/fetch_gemma_model.py "
            "(~2.5 GB); or litert-lm list then set LITERT_LM_MODEL"
        )
        sys.exit(2)
    if litert_lm is None:
        LOG.error("litert_lm import failed: %s", _LITERT_IMPORT_ERROR)
        sys.exit(2)

    try:
        mqtt_cfg = cfg.load_mqtt_config()
    except FileNotFoundError as e:
        LOG.error("%s", e)
        sys.exit(2)
    except ValueError as e:
        LOG.error("invalid config: %s", e)
        sys.exit(2)

    host = _env("MQTT_HOST", "").strip() or mqtt_cfg.broker_host
    if not host:
        LOG.error("mqtt broker host missing — set mqtt.broker_host in config.toml or MQTT_HOST")
        sys.exit(2)

    if os.environ.get("MQTT_PORT", "").strip():
        port = _env_int("MQTT_PORT", mqtt_cfg.port)
    else:
        port = mqtt_cfg.port

    sub_topic = _env("MQTT_SUBSCRIBE", "").strip() or mqtt_cfg.subscribe_pattern
    cid = _env("MQTT_CLIENT_ID", "").strip() or mqtt_cfg.client_id

    if "AGENT_MQTT_PUBLISH_TOPIC" in os.environ:
        publish_topic = os.environ.get("AGENT_MQTT_PUBLISH_TOPIC", "").strip() or None
    else:
        publish_topic = mqtt_cfg.publish_topic

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=cid,
    )

    engine_cm = build_engine(model_path)
    engine = engine_cm.__enter__()

    def on_connect(
        c: mqtt.Client,
        userdata: Any,
        connect_flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        if hasattr(reason_code, "is_failure"):
            connect_ok = not reason_code.is_failure
        else:
            try:
                connect_ok = int(reason_code) == 0
            except (TypeError, ValueError):
                connect_ok = True
        if not connect_ok:
            LOG.error("mqtt connect failed: %s", reason_code)
            return
        LOG.info("mqtt connected, subscribe %s", sub_topic)
        c.subscribe(sub_topic, qos=_env_int("MQTT_SUBSCRIBE_QOS", 1))

    client.on_connect = on_connect
    client.on_message = make_on_message(engine, publish_topic)

    try:
        LOG.info("connect mqtt %s:%s model=%s", host, port, model_path)
        try:
            client.connect(host, port, keepalive=_env_int("MQTT_KEEPALIVE", 60))
        except ConnectionRefusedError:
            LOG.error(
                "mqtt broker refused connection at %s:%s — nothing listening. "
                "Start a broker or fix mqtt.broker_host in config.toml (use hostname). "
                "Override: MQTT_HOST / MQTT_PORT.",
                host,
                port,
            )
            sys.exit(1)
        client.loop_forever()
    finally:
        try:
            engine_cm.__exit__(None, None, None)
        except Exception as e:
            LOG.warning("engine shutdown: %s", e)


if __name__ == "__main__":
    main()
