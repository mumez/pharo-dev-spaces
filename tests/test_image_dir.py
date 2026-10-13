from pds.image_dir import copy_image, remove_iceberg_cache


def make_image_dir(path):
    path.mkdir(parents=True)
    (path / "Pharo.image").write_text("image")
    (path / "Pharo.changes").write_text("changes")
    (path / "pharo-local" / "iceberg").mkdir(parents=True)
    return path


def test_copy_image_copies_image_and_changes_only(layout, tmp_path):
    source_dir = make_image_dir(tmp_path / "source")
    make_image_dir(layout.plain_dir)
    (layout.plain_dir / "Pharo14.0-64bit-abc.sources").write_text("sources")

    copy_image(layout, source_dir, tmp_path / "target")

    target_dir = tmp_path / "target"
    assert (target_dir / "Pharo.image").read_text() == "image"
    assert (target_dir / "Pharo.changes").read_text() == "changes"
    assert not (target_dir / "pharo-local").exists()


def test_copy_image_links_sources_of_plain_pharo(layout, tmp_path):
    source_dir = make_image_dir(tmp_path / "source")
    make_image_dir(layout.plain_dir)
    plain_sources = layout.plain_dir / "Pharo14.0-64bit-abc.sources"
    plain_sources.write_text("sources")

    copy_image(layout, source_dir, tmp_path / "target")

    linked_sources = tmp_path / "target" / "Pharo14.0-64bit-abc.sources"
    assert linked_sources.is_symlink()
    assert linked_sources.resolve() == plain_sources.resolve()


def test_remove_iceberg_cache_deletes_only_iceberg(tmp_path):
    image_dir = make_image_dir(tmp_path / "image")
    (image_dir / "pharo-local" / "package-cache").mkdir()

    remove_iceberg_cache(image_dir)

    assert not (image_dir / "pharo-local" / "iceberg").exists()
    assert (image_dir / "pharo-local" / "package-cache").exists()


def test_remove_iceberg_cache_accepts_missing_cache(tmp_path):
    remove_iceberg_cache(tmp_path)
