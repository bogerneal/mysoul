import json
import socket

import pytest

from weather.__main__ import main
from weather.config import ConfigurationError, Settings


def test_demo_needs_no_key_and_key_is_not_in_repr():
    assert Settings.from_env({}).mode == "demo"
    settings = Settings.from_env({"CWA_API_KEY": "sensitive-test-value"})
    assert "sensitive-test-value" not in repr(settings)


@pytest.mark.parametrize(
    "env", [{"WEATHER_MODE": "unknown"}, {"WEATHER_MODE": "live", "CWA_API_KEY": " "}]
)
def test_invalid_configuration_is_rejected(env):
    with pytest.raises(ConfigurationError):
        Settings.from_env(env)


def test_demo_cli_is_offline_and_labels_output(monkeypatch, capsys):
    monkeypatch.setenv("WEATHER_MODE", "demo")
    monkeypatch.delenv("CWA_API_KEY", raising=False)

    def deny_network(*args, **kwargs):
        raise AssertionError("Demo must not access the network")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    assert main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert "SYNTHETIC" in output["notice"]
    assert output["period_count"] == 4
    assert output["snapshot"]["mode"] == "demo"


def test_live_mode_cannot_silently_fall_back_to_demo(monkeypatch, capsys):
    monkeypatch.setenv("WEATHER_MODE", "live")
    monkeypatch.setenv("CWA_API_KEY", "sensitive-test-value")
    assert main([]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "not implemented" in output.err
    assert "sensitive-test-value" not in output.err


def test_malformed_file_error_does_not_expose_contents(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WEATHER_MODE", "demo")
    fixture = tmp_path / "bad.json"
    fixture.write_text('secret-content {"broken":', encoding="utf-8")
    assert main(["--fixture", str(fixture)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == "Error: cannot_read_fixture_json"


def test_custom_fixture_contract_error(tmp_path, document, monkeypatch, capsys):
    monkeypatch.setenv("WEATHER_MODE", "demo")
    document["schema_version"] = "secret-content"
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(document), encoding="utf-8")
    assert main(["--fixture", str(fixture)]) == 2
    assert capsys.readouterr().err.strip() == "Error: unsupported_schema"
