from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import main as m


def _fake_conv(text: str) -> MagicMock:
    conv = MagicMock()
    conv.__enter__.return_value = conv
    conv.send_message.return_value = {"content": [{"text": text}]}
    return conv


def test_run_inference_smoke() -> None:
    text = (
        '{"event":"reading","severity":"info","sensor":"temp",'
        '"reading":{"value":22,"unit":"C","raw":{}},'
        '"metadata":{"rules_triggered":[],"notes":"ok","mqtt_topic":""}}'
    )
    engine = MagicMock()
    engine.create_conversation.return_value = _fake_conv(text)
    out = m.run_inference(
        engine,
        topic="pi/sensor/temp",
        sensor="temp",
        payload={"value": 22},
        rules=[],
    )
    assert out["sensor"] == "temp"
    assert "metadata" in out


def test_run_inference_bad_json() -> None:
    engine = MagicMock()
    engine.create_conversation.return_value = _fake_conv("not json")
    with pytest.raises(ValueError):
        m.run_inference(
            engine,
            topic="pi/sensor/temp",
            sensor="temp",
            payload={"value": 1},
            rules=[],
        )


def test_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MQTT_HOST", raising=False)
    assert m._env("MQTT_HOST", "127.0.0.1") == "127.0.0.1"
    assert m._env_int("MQTT_PORT", 1883) == 1883


def test_env_int_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_PORT", "8883")
    assert m._env_int("MQTT_PORT", 1883) == 8883


def test_build_engine_wires_litert(monkeypatch: pytest.MonkeyPatch) -> None:
    lm = MagicMock()
    lm.LogSeverity.ERROR = 0
    lm.Backend.CPU = 0
    eng = MagicMock()
    lm.Engine.return_value = eng
    monkeypatch.setattr(m, "litert_lm", lm)
    monkeypatch.setattr(m, "_LITERT_IMPORT_ERROR", None)
    out = m.build_engine("/tmp/m.litertlm")
    assert out is eng
    lm.Engine.assert_called_once()


def test_build_engine_no_litert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m, "litert_lm", None)
    err = ImportError("nope")
    monkeypatch.setattr(m, "_LITERT_IMPORT_ERROR", err)
    with pytest.raises(RuntimeError):
        m.build_engine("/x")


def test_main_exits_without_model_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m.os.path, "isfile", lambda _p: False)
    called: list[int] = []

    def _exit(code: int) -> None:
        called.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(m.sys, "exit", _exit)
    with pytest.raises(SystemExit):
        m.main()
    assert called == [2]


def test_main_runs_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m.os.path, "isfile", lambda _p: True)
    lm = MagicMock()
    lm.LogSeverity.ERROR = 0
    lm.Backend.CPU = 0
    engine_ctx = MagicMock()
    engine_inner = MagicMock()
    engine_ctx.__enter__.return_value = engine_inner
    engine_ctx.__exit__.return_value = None
    lm.Engine.return_value = engine_ctx
    monkeypatch.setattr(m, "litert_lm", lm)
    monkeypatch.setattr(m, "_LITERT_IMPORT_ERROR", None)

    mc = MagicMock()

    def _client(**_k: object) -> MagicMock:
        return mc

    monkeypatch.setattr(m.mqtt, "Client", _client)
    mc.loop_forever.side_effect = lambda: None
    m.main()
    mc.connect.assert_called_once()
    mc.loop_forever.assert_called_once()
    engine_ctx.__exit__.assert_called_once()


def test_main_connect_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m.os.path, "isfile", lambda _p: True)
    lm = MagicMock()
    lm.LogSeverity.ERROR = 0
    lm.Backend.CPU = 0
    engine_ctx = MagicMock()
    engine_inner = MagicMock()
    engine_ctx.__enter__.return_value = engine_inner
    engine_ctx.__exit__.return_value = None
    lm.Engine.return_value = engine_ctx
    monkeypatch.setattr(m, "litert_lm", lm)
    monkeypatch.setattr(m, "_LITERT_IMPORT_ERROR", None)
    mc = MagicMock()
    monkeypatch.setattr(m.mqtt, "Client", lambda **_k: mc)
    mc.connect.side_effect = ConnectionRefusedError()
    called: list[int] = []

    def _exit(code: int) -> None:
        called.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(m.sys, "exit", _exit)
    with pytest.raises(SystemExit):
        m.main()
    assert called == [1]
    engine_ctx.__exit__.assert_called_once()


def test_on_message_publishes() -> None:
    text = (
        '{"event":"reading","severity":"info","sensor":"temp",'
        '"reading":{"value":22,"unit":"C","raw":{}},'
        '"metadata":{"rules_triggered":[],"notes":"ok","mqtt_topic":""}}'
    )
    engine = MagicMock()
    engine.create_conversation.return_value = _fake_conv(text)
    cb = m.make_on_message(engine, "out/events")
    client = MagicMock()
    msg = MagicMock()
    msg.topic = "pi/sensor/temp"
    msg.payload = b'{"value":22}'
    cb(client, None, msg)
    client.publish.assert_called_once()
    assert client.publish.call_args[0][0] == "out/events"


def test_on_message_skips_bad_topic() -> None:
    engine = MagicMock()
    cb = m.make_on_message(engine, None)
    client = MagicMock()
    msg = MagicMock()
    msg.topic = "wrong/topic"
    msg.payload = b"{}"
    cb(client, None, msg)
    engine.create_conversation.assert_not_called()


def test_on_message_inference_error(capfd: pytest.CaptureFixture[str]) -> None:
    engine = MagicMock()
    engine.create_conversation.side_effect = RuntimeError("boom")
    cb = m.make_on_message(engine, None)
    client = MagicMock()
    msg = MagicMock()
    msg.topic = "pi/sensor/temp"
    msg.payload = b'{"value":99}'
    cb(client, None, msg)
    out = capfd.readouterr().out
    assert "inference_error" in out
