# pi-agent-lm

Edge agent: MQTT sensor topics → LiteRT-LM (Gemma 4 E2B) → JSON on stdout (optional MQTT publish).

**License:** [MIT](LICENSE).

**AI-assisted development:** Much of this repository was produced with **AI coding assistance** (interactive agents / copilots). You should **review and test** before production use. Naming a specific vendor or product is **not required** when you fork or redistribute.

## Security notes (read before exposing to a network)

- **MQTT:** The app connects to your broker with **no application-level auth** — use broker **TLS**, **username/password**, **ACLs**, and **firewall rules** if the broker is reachable beyond localhost. Default setups in docs are for **local development**.
- **Trust boundaries:** MQTT payloads and topics are passed into a **local LLM**. Treat publishers you trust; malicious payloads could try to **influence model output** (prompt-style abuse). This is **not** a substitute for safety interlocks on physical equipment.
- **Dependencies:** Model weights are downloaded from **Hugging Face** (public repo); Python deps from **PyPI** — use pinned locks (`uv.lock`) and verify sources in sensitive deployments.
- **Secrets:** Do not commit API keys, broker passwords, or private model paths with credentials. Use environment variables.

See [SECURITY.md](SECURITY.md) for a short threat-model summary.

## How to run

Need **Python 3.10+** (LiteRT-LM wheels). Repo pins **3.12** in `.python-version` — `uv` uses that.

```bash
cd /path/to/pi-agent-lm
cp config.example.toml config.toml
# Set mqtt.broker_host to a real hostname (e.g. your Mosquitto host).
uv sync --extra litert --group dev
```

Put **Gemma 4 E2B** LiteRT-LM file next to `main.py` as `gemma-4-E2B-it.litertlm`, or set `LITERT_LM_MODEL` to full path. The file is **~2.5 GB** (not in git — see `.gitignore`).

**Official CLI (same as [LiteRT-LM on GitHub](https://github.com/google-ai-edge/LiteRT-LM))** — downloads and runs once (use `uv tool install litert-lm` first, or `uv tool run litert-lm` without a global install):

```bash
litert-lm run \
  --from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm \
  gemma-4-E2B-it.litertlm \
  --prompt="What is the capital of France?"
```

That proves the toolchain; the model may live in LiteRT’s store. For **main.py**, either point `LITERT_LM_MODEL` at the path from `litert-lm list`, or drop the file in this directory:

```bash
uv run python scripts/fetch_gemma_model.py
```

That writes `gemma-4-E2B-it.litertlm` here. **No Hugging Face account or token** — public repo; anonymous download.

You may still see Hub text like *“unauthenticated requests … set HF_TOKEN”* — that only means you’re not logged in. **Safe to ignore** for this public model unless a download actually fails or gets rate-limited.

**Alternative:** import into LiteRT’s store, then set env from `litert-lm list`:

```bash
uv tool run litert-lm import --from-huggingface-repo=litert-community/gemma-4-E2B-it-litert-lm gemma-4-E2B-it.litertlm
```

### Config (`config.toml`)

Broker hostname, ports, topics, and water-sensor pins live in **`config.toml`** (not in source). **`config.toml` is gitignored** — copy from **`config.example.toml`** and set a real **hostname** for `mqtt.broker_host` (avoid raw IPs in repo and docs where possible). Optional: `PI_AGENT_LM_CONFIG` points at a different file.

On a **Raspberry Pi**, use **`uv`** the same way as on a dev machine (`uv sync`, `uv run`). Copy config over with **scp** using the Pi **hostname**, e.g. `scp config.toml r0nc0d3r@r0nh0m5.local:~/pi-agent-lm/` (adjust path if needed).

Subscribe pattern default in the example file is **`pi/sensor/#`**. Publish test message (use your broker hostname or `localhost` if Mosquitto is on the same machine):

```bash
mosquitto_pub -h localhost -t pi/sensor/temp -m '{"value":41,"unit":"C"}'
```

Run agent (needs `config.toml` in the working directory):

```bash
uv run main.py
```

**Water flow / leak (YF-S201) on the Pi** lives in a **standalone uv project**: **[`flow_sensor/`](flow_sensor/)** — its own **`pyproject.toml`**, **`.venv`** from **`uv sync`**, and deploy path **`~/Documents/flow_sensor/`** on the Pi (**`r0nh0m5.local`** in our setup; dev / broker **`r0n4k.local`**). See **[flow_sensor/README.md](flow_sensor/README.md)** for **`scp`**, **`uv sync --extra pi`**, and **`uv run python water_sensor.py`**. Wiring: **[flow_sensor/WATER_SENSOR_README.md](flow_sensor/WATER_SENSOR_README.md)**.

Each MQTT message prints **one JSON line** (UTF-8). Optional: also publish that JSON string to a topic:

```bash
export AGENT_MQTT_PUBLISH_TOPIC=pi/agent/events
uv run main.py
```

Useful env vars:


| var                        | default                   | note                        |
| -------------------------- | ------------------------- | --------------------------- |
| `LITERT_LM_MODEL`          | `gemma-4-E2B-it.litertlm` | path to `.litertlm`         |
| `LITERT_LM_CACHE_DIR`      | (none)                    | cache for compiled bits     |
| `PI_AGENT_LM_CONFIG`       | (none)                    | path to alternate TOML (`flow_sensor/`: also `FLOW_SENSOR_CONFIG`) |
| `MQTT_HOST`                | (from `config.toml`)      | overrides `mqtt.broker_host` |
| `MQTT_PORT`                | (from `config.toml`)      | overrides `mqtt.port`       |
| `MQTT_SUBSCRIBE`           | (from `config.toml`)      | overrides subscribe pattern |
| `MQTT_CLIENT_ID`           | (from `config.toml`)      | MQTT client id              |
| `AGENT_MQTT_PUBLISH_TOPIC` | (from `config.toml`)      | if set in env, overrides `mqtt.publish_topic` |
| `AGENT_MQTT_PUBLISH_QOS`   | `1`                       |                             |
| `AGENT_REGION`             | `north-west India`        | climate context for the LLM |
| `AGENT_TIMEZONE`           | `Asia/Kolkata`            | local date / season hints   |


Temperature / humidity **severity is decided by the model** using `AGENT_REGION`, local season (from `AGENT_TIMEZONE`), and optional payload fields. Objective MQTT hints: `water_leak`, `flow_stalled` still bump severity floors.

### Optional MQTT JSON (publish richer context)

Same topic (e.g. `pi/sensor/temp`); body is JSON. Helpful keys (all optional):


| field                 | purpose                                            |
| --------------------- | -------------------------------------------------- |
| `location`            | `indoor` / `outdoor` / `mixed` — indoor vs ambient |
| `outdoor_temp`        | ambient °C for contrast with indoor reading        |
| `time_of_day`         | `morning` / `afternoon` / `evening` / `night`      |
| `weather`             | short text or code (clear, rain, …)                |
| `heat_index`          | number if known                                    |
| `forecast`            | short string                                       |
| `occupant_vulnerable` | `true` if elderly/infant/medical heat or cold risk |
| `cooling_active`      | `true` if AC/cooling known on                      |
| `heating_active`      | `true` if heating known on                         |


Example:

```bash
mosquitto_pub -h localhost -t pi/sensor/temp -m \
  '{"value":16,"unit":"C","location":"indoor","cooling_active":true,"outdoor_temp":41}'
```

### Output `event` field (canonical)

The model is steered toward these **`event`** strings (normalized after inference):  
`temperature_reading`, `heat_alert`, `cold_alert`, `humidity_reading`, `water_leak`, `flow_stalled`, `general_reading`.

Tests + coverage gate:

```bash
uv run pytest --cov=main --cov=sensor_logic --cov=agent_settings --cov=flow_sensor_math --cov-report=term-missing --cov-fail-under=80 -q
```

## Recent changes

- **Git branches:** use **`agent/`** prefix for new work branches (not **`cursor/`** or **`claude/`** or **`codex/`**);
- **Water sensor:** Default **`GPIOZERO_PIN_FACTORY=rpigpio`** when **`lgpio`** missing (quieter logs); poll interval **1 ms** (lighter CPU); **`python -u`** in README for **`sensor.log`**.
- **Config:** `config.toml` + `config.example.toml` (`agent_settings.py`); broker host/topics/pins not hardcoded — env vars override for dev/CI; `config.toml` gitignored; docs + rule: hostnames for MQTT/SSH/scp, **uv** on Pi.
- **Agent / docs:** prefer **uv** for all Python CLI (`uv run`, `uv add`, `uvx`); `.agent/rules/uv-cli.mdc` + tests rule updated; water sensor uses **`flow_sensor/`** + `uv sync --extra pi`; pytest includes **`flow_sensor_math`** coverage.
- Wired `main.py`: Paho MQTT `pi/sensor/#`, LiteRT-LM Gemma 4 E2B inference, JSON output + optional publish topic; `sensor_logic.py` for parse/rules/merge; tests + `pyproject` optional `litert` extra; Python **≥3.10**; `.python-version` **3.12**.
- Added `scripts/fetch_gemma_model.py` + `huggingface-hub` dep so model file can land in repo root; clearer missing-model errors; `*.litertlm` gitignored; docs match upstream `litert-lm run` + France prompt; no HF token needed for public model; README explains HF “unauthenticated” warning is normal.
- Temp/humidity alerts use **region + season context** (`AGENT_REGION`, `AGENT_TIMEZONE`) for LLM judgment; fixed °C threshold removed; water/flow objective rules kept.
- **Payload schema hints** + **indoor/AC severity nudge** in prompts; **canonical `event`** enum + post-merge normalization; README documents optional MQTT JSON and event values.
- **MIT** `LICENSE`, **SECURITY.md**, README security + AI-assistance notice; `.gitignore` extended for LiteRT XNNPack cache; `pyproject` description + license metadata.

