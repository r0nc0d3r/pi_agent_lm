# Security considerations

This project is intended for **local / lab / trusted-LAN** use unless you harden it.

## MQTT

- Uses **cleartext MQTT by default** (`paho-mqtt` to host/port from `**config.toml`** or env overrides). For anything beyond a trusted network, configure your broker for **TLS** (`mqtts://` / port 8883) and **authentication**; you may need code changes to pass TLS options to the client. Keep real broker hostnames out of git (`config.toml` is gitignored; use `config.example.toml` for placeholders).
- **Access control** (who can publish/subscribe) must be enforced at the **broker** (ACLs, bridges), not in this repo.

## Model and supply chain

- The optional **LiteRT-LM** wheel and **Gemma** weights come from **PyPI** / **Hugging Face**. Verify checksums and organizational policies before deploying in regulated environments.
- **Large `.litertlm` files** are not committed; download scripts pull public artifacts.

## LLM behavior

- Outputs are **not cryptographically verified** and can be **wrong or inconsistent**. Do not use as the only input for safety-critical actuators without independent checks.
- **Untrusted MQTT publishers** should not be allowed to drive actuators based solely on model JSON without validation.

## Reporting

If you find a **security vulnerability** in this repository’s code, please open a private report or issue per the maintainer’s preference once the repo is public.