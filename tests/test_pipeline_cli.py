import json

from weather.pipeline_cli import main


def test_demo_import_and_query(tmp_path, capsys):
    db = str(tmp_path / "weather.sqlite3")
    assert main(["update-demo", "--db", db]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["update-demo", "--db", db]) == 0
    assert json.loads(capsys.readouterr().out)["batch_id"] == first["batch_id"]
    assert main(["status", "--db", db, "--mode", "demo"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert len(state["snapshot"]["periods"]) == 4
    assert state["notice"] == "SYNTHETIC DATA"
    assert main(["status", "--db", db, "--mode", "live"]) == 0
    assert json.loads(capsys.readouterr().out)["snapshot"] is None


def test_malformed_fixture_retains_data(tmp_path, capsys):
    db = str(tmp_path / "weather.sqlite3")
    main(["update-demo", "--db", db])
    capsys.readouterr()
    fixture = tmp_path / "bad.json"
    fixture.write_text("secret-invalid-json", encoding="utf-8")
    assert main(["update-demo", "--db", db, "--fixture", str(fixture)]) == 2
    assert capsys.readouterr().err.strip() == "Error: cannot_read_fixture_json"
    main(["status", "--db", db, "--mode", "demo"])
    state = json.loads(capsys.readouterr().out)
    assert state["last_error_code"] == "update_failed"
    assert len(state["snapshot"]["periods"]) == 4


def test_capture_stays_private_and_does_not_publish(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CWA_API_KEY", "secret")
    monkeypatch.setattr("weather.pipeline_cli.fetch_weekly", lambda key: {"records": {}})
    assert main(["capture-cwa"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "captured_unverified"
    assert "secret" not in (tmp_path / result["path"]).read_text()
    assert not (tmp_path / "data/weather.sqlite3").exists()


def test_capture_rejects_echoed_key(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CWA_API_KEY", "secret")
    monkeypatch.setattr("weather.pipeline_cli.fetch_weekly", lambda key: {"echo": key})
    assert main(["capture-cwa"]) == 2
    assert "response_contains_credential" in capsys.readouterr().err
    assert not (tmp_path / "data/private").exists()
