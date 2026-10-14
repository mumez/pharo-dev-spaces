import pytest

from pds import dev_base
from pds.dev_base import prepare_dev_base, run_dev_base
from pds.pharo import PharoRunError
from tests.test_image_dir import make_image_dir


@pytest.fixture
def plain_layout(layout):
    make_image_dir(layout.plain_dir)
    (layout.plain_dir / "Pharo14.0-64bit-abc.sources").write_text("sources")
    return layout


def fake_successful_run(layout, image, script, port, timeout, save=False):
    assert save is None
    assert script.name == "load_agentic_browser.st"
    (image.parent / "pharo-local" / "iceberg" / "Sis").mkdir(parents=True)


def test_prepare_dev_base_creates_image_without_iceberg_cache(plain_layout, monkeypatch):
    monkeypatch.setattr(dev_base, "run_pharo", fake_successful_run)

    prepare_dev_base(plain_layout)

    assert (plain_layout.dev_base_dir / "Pharo.image").exists()
    assert not (plain_layout.dev_base_dir / "pharo-local" / "iceberg").exists()


def test_prepare_dev_base_leaves_nothing_behind_on_failure(plain_layout, monkeypatch):
    def failing_run(*args, **kwargs):
        raise PharoRunError("load failed")

    monkeypatch.setattr(dev_base, "run_pharo", failing_run)

    with pytest.raises(PharoRunError):
        prepare_dev_base(plain_layout)

    assert list(plain_layout.root.glob("dev-base*")) == []


def test_prepare_dev_base_refuses_to_overwrite_without_force(plain_layout):
    plain_layout.dev_base_dir.mkdir()

    with pytest.raises(FileExistsError):
        prepare_dev_base(plain_layout)


def test_prepare_dev_base_replaces_existing_when_forced(plain_layout, monkeypatch):
    plain_layout.dev_base_dir.mkdir()
    (plain_layout.dev_base_dir / "stale").write_text("stale")
    monkeypatch.setattr(dev_base, "run_pharo", fake_successful_run)

    prepare_dev_base(plain_layout, force=True)

    assert not (plain_layout.dev_base_dir / "stale").exists()
    assert (plain_layout.dev_base_dir / "Pharo.image").exists()


def test_run_dev_base_requires_prepared_image(layout):
    with pytest.raises(FileNotFoundError, match="prepare-dev-base"):
        run_dev_base(layout)


def test_run_dev_base_launches_gui_on_standalone_port(plain_layout, monkeypatch):
    make_image_dir(plain_layout.dev_base_dir)
    calls = []
    monkeypatch.setattr(dev_base, "launch_pharo_ui", lambda layout, image, port: calls.append((image, port)))

    run_dev_base(plain_layout)

    assert calls == [(plain_layout.dev_base_dir / "Pharo.image", 8086)]
