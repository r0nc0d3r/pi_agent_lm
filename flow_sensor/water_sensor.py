import json
import os
import threading
import time
from typing import Literal

import paho.mqtt.client as mqtt

from agent_settings import load_water_sensor_bundle
from flow_sensor_math import (
    flow_rate_lpm,
    liters_over_interval,
    poll_increment_if_rising,
)

# Pin factory before gpiozero import: lgpio if present, else RPi.GPIO (quieter than full fallback chain).
if "GPIOZERO_PIN_FACTORY" not in os.environ:
    try:
        import importlib.util

        if importlib.util.find_spec("lgpio") is not None:
            os.environ["GPIOZERO_PIN_FACTORY"] = "lgpio"
        elif importlib.util.find_spec("RPi") is not None:
            os.environ["GPIOZERO_PIN_FACTORY"] = "rpigpio"
    except Exception:
        pass

pulse_count = 0
total_liters = 0.0
_pulse_lock = threading.Lock()

# Open-collector flow meter with pull-up: line idles HIGH, pulse pulls LOW.
# Count LOW → HIGH (rising) = one pulse (matches gpiozero when_activated, active_high).


def pulse_callback() -> None:
    global pulse_count
    with _pulse_lock:
        pulse_count += 1


def _try_gpiozero(
    pin_flow: int, pin_leak: int
) -> tuple[Literal["gpiozero"], object, object] | None:
    from gpiozero import DigitalInputDevice

    try:
        flow_dev = DigitalInputDevice(
            pin_flow,
            pull_up=True,
            bounce_time=None,
        )
        flow_dev.when_activated = pulse_callback
        leak_dev = DigitalInputDevice(pin_leak, pull_up=True, bounce_time=None)
        return ("gpiozero", flow_dev, leak_dev)
    except (RuntimeError, OSError):
        try:
            flow_dev.close()
        except Exception:
            pass
        return None


class RpiGpioPollBackend:
    """Flow pulses via polling (no add_event_detect). Leak read in main loop."""

    def __init__(self, pin_flow: int, pin_leak: int, poll_interval_s: float = 1e-3):
        import RPi.GPIO as GPIO  # type: ignore[import-untyped]

        self._GPIO = GPIO
        self._pin_flow = pin_flow
        self._pin_leak = pin_leak
        self._stop = threading.Event()
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin_flow, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(pin_leak, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._thr = threading.Thread(
            target=self._poll_flow_loop,
            args=(poll_interval_s,),
            daemon=True,
        )
        self._thr.start()

    def _poll_flow_loop(self, poll_interval_s: float) -> None:
        global pulse_count
        GPIO = self._GPIO
        pin = self._pin_flow
        last = 1 if GPIO.input(pin) else 0
        while not self._stop.is_set():
            level = 1 if GPIO.input(pin) else 0
            delta, last = poll_increment_if_rising(last, level)
            if delta:
                with _pulse_lock:
                    pulse_count += delta
            if self._stop.wait(poll_interval_s):
                break

    def leak_is_wet(self) -> bool:
        return self._GPIO.input(self._pin_leak) == self._GPIO.LOW

    def close(self) -> None:
        self._stop.set()
        self._thr.join(timeout=2.0)
        self._GPIO.cleanup()


def main() -> None:
    global pulse_count, total_liters

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

    gpio_mode: Literal["gpiozero", "rpigpio_poll"]
    flow_dev: object | None = None
    leak_dev: object | None = None
    poll_backend: RpiGpioPollBackend | None = None

    gz = _try_gpiozero(ws.pin_flow_bcm, ws.pin_leak_bcm)
    if gz is not None:
        gpio_mode = "gpiozero"
        _, flow_dev, leak_dev = gz
        print("GPIO: gpiozero (interrupt mode)")
    else:
        try:
            poll_backend = RpiGpioPollBackend(ws.pin_flow_bcm, ws.pin_leak_bcm)
        except ImportError:
            print(
                "GPIO: edge detection failed and RPi.GPIO is not installed. "
                "Install: sudo apt install python3-dev && uv pip install RPi.GPIO"
            )
            client.disconnect()
            return
        gpio_mode = "rpigpio_poll"
        print(
            "GPIO: RPi.GPIO polling fallback (edge detection unavailable on this OS)"
        )

    print("Starting Real Water Sensor...")
    print(f"Flow Pin: {ws.pin_flow_bcm}, Leak Pin: {ws.pin_leak_bcm}")
    print(f"Publishing to {ws.topic_flow} and {ws.topic_leak}")

    last_time = time.time()
    last_leak_state: bool | None = None

    try:
        while True:
            current_time = time.time()
            elapsed = current_time - last_time

            if elapsed >= 2.0:
                with _pulse_lock:
                    pc = pulse_count
                rate_lpm = flow_rate_lpm(
                    pulse_count=pc, elapsed_s=elapsed, pulse_k=ws.pulse_k
                )
                liters_this_interval = liters_over_interval(
                    rate_lpm=rate_lpm, elapsed_s=elapsed
                )
                total_liters += liters_this_interval

                payload = {
                    "value": round(rate_lpm, 2),
                    "total_liters": round(total_liters, 2),
                    "unit": "L/min",
                    "location": ws.location,
                }
                client.publish(ws.topic_flow, json.dumps(payload))
                print(f"[FLOW] {rate_lpm:.2f} L/min | Total: {total_liters:.2f} L")

                with _pulse_lock:
                    pulse_count = 0
                last_time = current_time

            if gpio_mode == "gpiozero":
                assert leak_dev is not None
                is_leaking = not leak_dev.is_active  # type: ignore[union-attr]
            else:
                assert poll_backend is not None
                is_leaking = poll_backend.leak_is_wet()

            if is_leaking != last_leak_state:
                payload_leak = {
                    "leak": is_leaking,
                    "location": ws.location,
                }
                client.publish(ws.topic_leak, json.dumps(payload_leak))
                print(f"[LEAK] {'WET!' if is_leaking else 'Dry'}")
                last_leak_state = is_leaking

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopping sensor...")
    finally:
        if gpio_mode == "gpiozero":
            assert flow_dev is not None and leak_dev is not None
            flow_dev.close()
            leak_dev.close()
        else:
            assert poll_backend is not None
            poll_backend.close()
        client.disconnect()


if __name__ == "__main__":
    main()
