"""Publish fake flow/leak MQTT messages (dev). Broker + topics from config.toml."""

from __future__ import annotations

import json
import random
import time

import paho.mqtt.client as mqtt

from agent_settings import load_water_sensor_bundle


def publish_flow(
    client: mqtt.Client, topic: str, liters: float, rate_lpm: float, location: str
) -> None:
    payload = {
        "value": rate_lpm,
        "total_liters": liters,
        "unit": "L/min",
        "location": location,
    }
    client.publish(topic, json.dumps(payload))
    print(f"[FLOW] Published: {rate_lpm} L/min, Total: {liters:.2f} L")


def publish_leak(
    client: mqtt.Client, topic: str, is_leaking: bool, location: str
) -> None:
    payload = {
        "leak": is_leaking,
        "location": location,
    }
    client.publish(topic, json.dumps(payload))
    print(f"[LEAK] Published: {'LEAK!' if is_leaking else 'Dry'}")


def main() -> None:
    try:
        mqtt_cfg, ws = load_water_sensor_bundle()
    except FileNotFoundError as e:
        print(e)
        return
    except ValueError as e:
        print(f"invalid config: {e}")
        return

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    try:
        client.connect(mqtt_cfg.broker_host, mqtt_cfg.port)
    except Exception as e:
        print(f"Could not connect to MQTT broker at {mqtt_cfg.broker_host}: {e}")
        return

    print("Starting Water Flow Sensor Mock...")
    print(f"Publishing to {ws.topic_flow} and {ws.topic_leak}")

    total_liters = 0.0
    is_flowing = False

    try:
        while True:
            if not is_flowing:
                if random.random() < 0.1:
                    is_flowing = True
                    print("\n--- Water started flowing ---")
            else:
                if random.random() < 0.2:
                    is_flowing = False
                    print("\n--- Water stopped flowing ---")
                    publish_flow(client, ws.topic_flow, total_liters, 0.0, ws.location)

            if is_flowing:
                rate_lpm = random.uniform(1.0, 10.0)
                liters_this_sec = rate_lpm / 60.0
                total_liters += liters_this_sec
                publish_flow(
                    client, ws.topic_flow, total_liters, rate_lpm, ws.location
                )

            if random.random() < 0.05:
                publish_leak(client, ws.topic_leak, True, ws.location)
            elif random.random() < 0.1:
                publish_leak(client, ws.topic_leak, False, ws.location)

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping mock sensor...")
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
