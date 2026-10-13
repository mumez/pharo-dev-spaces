"""Operations on directories holding a Pharo.image / Pharo.changes pair."""

import shutil
from contextlib import contextmanager
from pathlib import Path

IMAGE_FILE_NAMES = ("Pharo.image", "Pharo.changes")


def image_path(image_dir):
    return Path(image_dir) / "Pharo.image"


def copy_image(layout, source_dir, target_dir):
    """Copy image + changes into target_dir and link the plain-pharo sources (shared, read-only)."""
    target_dir.mkdir(parents=True)
    for name in IMAGE_FILE_NAMES:
        shutil.copy2(source_dir / name, target_dir / name)
    for plain_sources in layout.plain_dir.glob("*.sources"):
        (target_dir / plain_sources.name).symlink_to(plain_sources.resolve())


def remove_iceberg_cache(image_dir):
    """Iceberg clones of Metacello dependencies are not needed after loading."""
    shutil.rmtree(Path(image_dir) / "pharo-local" / "iceberg", ignore_errors=True)


@contextmanager
def staged_replacement(target_dir, force=False):
    """Yield a staging dir that replaces target_dir on success and is discarded on failure."""
    if target_dir.exists() and not force:
        raise FileExistsError(f"{target_dir} already exists (use --force to replace it)")
    staging_dir = target_dir.with_name(target_dir.name + ".staging")
    shutil.rmtree(staging_dir, ignore_errors=True)
    try:
        yield staging_dir
    except BaseException:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    shutil.rmtree(target_dir, ignore_errors=True)
    staging_dir.rename(target_dir)
