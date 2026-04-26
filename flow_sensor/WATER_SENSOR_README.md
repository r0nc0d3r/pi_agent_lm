# Water flow sensor (YF-S201) on Raspberry Pi Zero v1.1

This wiring matches **`water_sensor.py`** in this folder when **`[water_sensor].pin_flow_bcm`** in `config.toml` is **17** (BCM **GPIO17** = **physical pin 11** on the 40-pin header).

## Sensor

- **Type:** water flow sensor  
- **Model:** **YF-S201**  
- Typical use: pulse output proportional to flow (see sensor datasheet; pulse scaling is configured as `pulse_k` in `config.toml`).

## How to put wires (flow sensor)

1. **Red Wire (Power)** → Put on **Pin 2** (5V)
2. **Black Wire (Ground)** → Put on **Pin 6** (GND)
3. **Yellow Wire (Signal)** → Put on **Pin 11** (GPIO 17)

On the 40-pin header, **pin 11** is **BCM GPIO 17**, which matches the default **`pin_flow_bcm = 17`** in `config.example.toml`.

**Header orientation:** Pin 1 is the square pad; use a [pinout diagram](https://pinout.xyz) if you are unsure which physical pin is which.

### Quick reference

| Physical pin | Pi function     | Wire   |
|-------------|-----------------|--------|
| **2**       | 5V              | Red    |
| **6**       | GND             | Black  |
| **11**      | GPIO17 (BCM 17) | Yellow |

Power: confirm your YF-S201 module’s voltage range (many are **5–18 V**; **5 V** from pin 2 is common).

## Software

- Copy **`config.example.toml`** to **`config.toml`** in **`~/Documents/flow_sensor/`** (or this project directory) and set **`mqtt.broker_host`** (hostname).
- On the Pi: **`uv sync --extra pi`** then **`uv run python water_sensor.py`** (see **[README.md](README.md)**).

Leak sensor pins are separate; set **`pin_leak_bcm`** in `config.toml` to match your wiring.

## Safety

- Double-check **5 V vs 3.3 V** for the signal line; if the sensor outputs **5 V pulses**, use a **level shifter** or a **voltage divider** so **GPIO17** never sees more than **3.3 V**.
