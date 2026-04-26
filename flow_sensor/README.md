# flow-sensor (YF-S201 on Raspberry Pi)

Standalone **`uv`** project: dependencies install into **`.venv`** in this directory. Deploy on the Pi under **`~/Documents/flow_sensor/`** (or any path you prefer).

## Hostnames (this setup)

| Machine        | mDNS hostname    | SSH user        | Role (example)        |
|----------------|------------------|-----------------|------------------------|
| Raspberry Pi   | **`r0nh0m5.local`** | **`r0nc0d3r`** | Runs `water_sensor.py` |
| Dev / broker   | **`r0n4k.local`**   | (your user)     | Mosquitto or other MQTT broker |

Adjust **`mqtt.broker_host`** in `config.toml` if your broker lives elsewhere.

## Pi Zero / **armv6l** — GPIO prerequisites (one-time, needs **sudo**)

On **`r0nh0m5.local`**, `gpiozero` needs a real pin backend. Without **`lgpio`** or **`RPi.GPIO`**, it falls back to **`NativeFactory`** and GPIO **fails** (`/sys/class/gpio/...`, `OSError: Invalid argument`).

If **`sensor.log`** shows **`RuntimeError: Failed to add edge detection`** (gpiozero / **`RPi.GPIO.add_event_detect`**), use a current **`water_sensor.py`**: it **falls back to RPi.GPIO polling** (no interrupts) automatically after gpiozero setup fails.

**Hardware unplugged:** With **internal pull-ups**, an open **flow** line usually sits **HIGH** (no pulses → ~0 L/min). A **floating leak** pin can flicker and trigger **Dry/WET** MQTT spam; connect the sensor or tie the leak line to **3.3 V** (dry) or **GND** (wet) until wired.

**Option A — RPi.GPIO (common on Pi Zero)** — install headers, then install into this project’s **`.venv`**:

```bash
sudo apt update
sudo apt install -y python3-dev
cd ~/Documents/flow_sensor
export PATH="$HOME/.local/bin:$PATH"
uv pip install "RPi.GPIO>=0.7.1"
```

Run with the RPi pin factory:

```bash
export GPIOZERO_PIN_FACTORY=rpigpio
export PATH="$HOME/.local/bin:$PATH"
nohup uv run python water_sensor.py >> sensor.log 2>&1 </dev/null &
```

**Option B — `lgpio`** (Pi 5 / Bookworm-friendly) — needs **SWIG** to build from PyPI:

```bash
sudo apt install -y swig python3-dev
cd ~/Documents/flow_sensor
export PATH="$HOME/.local/bin:$PATH"
uv sync --extra pi
```

Then start **`water_sensor.py`** as usual ( **`lgpio`** is auto-selected if importable).

## One-time on the Pi (`r0nh0m5.local`)

From your dev machine (**`r0n4k.local`**), copy the whole folder so **`pyproject.toml`** and **`water_sensor.py`** share the same directory (includes dotfiles like **`.python-version`**):

```bash
cd /path/to/pi-agent-lm
scp -r flow_sensor "r0nc0d3r@r0nh0m5.local:~/Documents/"
```

This creates **`~/Documents/flow_sensor/`** on the Pi. Alternatively:  
`rsync -avz flow_sensor/ "r0nc0d3r@r0nh0m5.local:~/Documents/flow_sensor/"`.

Then on the Pi over SSH:

```bash
ssh r0nc0d3r@r0nh0m5.local
cd ~/Documents/flow_sensor
cp config.example.toml config.toml
# Edit config.toml: mqtt.broker_host, pins, topics as needed.
uv sync --extra pi
uv run python water_sensor.py
```

- **`uv sync`** creates **`.venv`** here and installs `paho-mqtt`, `gpiozero`, and with **`--extra pi`** also **`lgpio`** (recommended on Pi 5 / Bookworm).
- **`uv run`** uses that venv automatically.

**Mock (no GPIO):** `uv run python mock_water_sensor.py`

## Deploy with **scp** + **ssh**, **`uv`**, **`nohup`**, **`sensor.log`**

From your dev machine (**`r0n4k.local`**), push the **whole** `flow_sensor` tree (not only `water_sensor.py` — the Pi needs **`pyproject.toml`**, **`agent_settings.py`**, **`flow_sensor_math.py`**, **`config.toml`**, etc.):

```bash
cd /path/to/pi-agent-lm
scp -r flow_sensor "r0nc0d3r@r0nh0m5.local:~/Documents/"
```

Copy **`config.toml`** if it only exists locally (example: after editing **`mqtt.broker_host`**):

```bash
scp flow_sensor/config.toml "r0nc0d3r@r0nh0m5.local:~/Documents/flow_sensor/config.toml"
```

Or create it on the Pi once: **`ssh r0nc0d3r@r0nh0m5.local`**, **`cd ~/Documents/flow_sensor`**, **`cp config.example.toml config.toml`**, edit, exit.

**Install deps and run `water_sensor.py` in the background** with **`nohup`**, append **stdout + stderr** to **`sensor.log`** in the same directory.

On **Pi Zero / armv6l**, use **`uv sync`** (no **`pi`** extra) **after** you have installed **`RPi.GPIO`** per the prerequisites above, and pass **`GPIOZERO_PIN_FACTORY=rpigpio`**:

```bash
ssh r0nc0d3r@r0nh0m5.local 'cd ~/Documents/flow_sensor && export PATH="$HOME/.local/bin:$PATH" && uv sync && GPIOZERO_PIN_FACTORY=rpigpio nohup uv run python water_sensor.py >> sensor.log 2>&1 </dev/null & echo "PID=$!"'
```

On **Pi 5 / Bookworm** where **`uv sync --extra pi`** (**`lgpio`**) works:

```bash
ssh r0nc0d3r@r0nh0m5.local 'cd ~/Documents/flow_sensor && export PATH="$HOME/.local/bin:$PATH" && uv sync --extra pi && nohup uv run python water_sensor.py >> sensor.log 2>&1 </dev/null & echo "PID=$!"'
```
```

- **`>> sensor.log`** — appends log lines (use **`> sensor.log`** if you want a fresh file each start).
- **`2>&1`** — includes Python tracebacks and prints in **`sensor.log`**.
- **`</dev/null`** — avoids **`nohup`** waiting on stdin.

**Follow the log on the Pi** (use **`-u`** so lines appear immediately):

```bash
nohup uv run python -u water_sensor.py >> sensor.log 2>&1 </dev/null &
ssh r0nc0d3r@r0nh0m5.local 'tail -f ~/Documents/flow_sensor/sensor.log'
```

If **`sensor.log`** only shows **`PinFactoryFallback: ... lgpio`** — that is a **warning**, not a crash. Current **`water_sensor.py`** sets **`GPIOZERO_PIN_FACTORY=rpigpio`** when **`lgpio`** is not installed so that line should stop after you **rsync** the update.

**Stop the process:** find the PID (from the **`echo`** above, or **`pgrep -af water_sensor`**) then **`kill <pid>`** on the Pi.

## Config

- **`FLOW_SENSOR_CONFIG`** — optional path to a TOML file instead of `./config.toml`.
- Same schema as repo root **`config.example.toml`**; this folder ships its own **`config.example.toml`** with example hostnames.

## Wiring (Pi Zero v1.1 + YF-S201)

See **[WATER_SENSOR_README.md](WATER_SENSOR_README.md)**.
