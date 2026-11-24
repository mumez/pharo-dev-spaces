from pds.layout import REPOSITORY_ROOT, Layout, resolved_root


def test_root_defaults_to_the_repository_pds_runs_from(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert resolved_root() == {"value": REPOSITORY_ROOT, "source": "default"}


def test_root_comes_from_pds_json(write_pds_json, tmp_path):
    config_file = write_pds_json()

    assert resolved_root() == {"value": tmp_path / "pds-root", "source": f"pds.json:{config_file}"}
    assert Layout.default().root == tmp_path / "pds-root"


def test_pds_root_environment_variable_beats_pds_json(write_pds_json, tmp_path, monkeypatch):
    write_pds_json()
    monkeypatch.setenv("PDS_ROOT", str(tmp_path))

    assert resolved_root() == {"value": tmp_path, "source": "env:PDS_ROOT"}
