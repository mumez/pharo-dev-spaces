import subprocess

import pytest

from pds.sources import SourceFetchError, baseline_changed, fetch_project_sources


def git(*arguments, cwd):
    return subprocess.run(["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def cloned_repository(tmp_path):
    """A clone whose origin has a develop branch ahead of the clone's working tree."""
    origin = tmp_path / "origin.git"
    git("init", "--bare", "-q", "-b", "develop", str(origin), cwd=tmp_path)
    author = tmp_path / "author"
    git("clone", "-q", str(origin), str(author), cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=author)
    git("config", "user.name", "t", cwd=author)
    (author / "src" / "Pkg").mkdir(parents=True)
    (author / "src" / "Pkg" / "package.st").write_text("Package { #name : 'Pkg' }")
    (author / "README.md").write_text("readme")
    git("add", ".", cwd=author)
    git("commit", "-q", "-m", "first", cwd=author)
    git("push", "-q", "origin", "develop", cwd=author)
    clone = tmp_path / "clone"
    git("clone", "-q", str(origin), str(clone), cwd=tmp_path)
    (author / "src" / "Pkg" / "Added.class.st").write_text("Class { #name : 'Added' }")
    git("add", ".", cwd=author)
    git("commit", "-q", "-m", "second", cwd=author)
    git("push", "-q", "origin", "develop", cwd=author)
    return {"clone": clone, "latest_sha": git("rev-parse", "HEAD", cwd=author)}


def project(repository):
    return {"repository": str(repository), "baseline": "Pkg", "srcDir": "src", "groups": ["default"], "packages": []}


def test_fetches_latest_origin_develop_and_extracts_src_dir(cloned_repository, tmp_path):
    [fetched] = fetch_project_sources([project(cloned_repository["clone"])], tmp_path / "extracted")

    assert fetched.sha == cloned_repository["latest_sha"]
    assert (fetched.src_path / "Pkg" / "Added.class.st").exists()
    assert not (fetched.src_path.parent / "README.md").exists()


def test_does_not_touch_working_tree_or_branch(cloned_repository, tmp_path):
    clone = cloned_repository["clone"]
    head_before = git("rev-parse", "HEAD", cwd=clone)

    fetch_project_sources([project(clone)], tmp_path / "extracted")

    assert git("rev-parse", "HEAD", cwd=clone) == head_before
    assert not (clone / "src" / "Pkg" / "Added.class.st").exists()


def test_missing_origin_develop_is_reported_with_repository(tmp_path):
    repository = tmp_path / "plain"
    git("init", "-q", str(repository), cwd=tmp_path)

    with pytest.raises(SourceFetchError, match=str(repository)):
        fetch_project_sources([project(repository)], tmp_path / "extracted")


def commit_file(repository, relative_path, content):
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git("add", ".", cwd=repository)
    git("commit", "-q", "-m", f"change {relative_path}", cwd=repository)
    return git("rev-parse", "HEAD", cwd=repository)


@pytest.fixture
def repository(tmp_path):
    repository = tmp_path / "repository"
    git("init", "-q", str(repository), cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=repository)
    git("config", "user.name", "t", cwd=repository)
    return repository


def test_baseline_change_is_detected(repository):
    old_sha = commit_file(repository, "src/BaselineOfPkg/BaselineOfPkg.class.st", "v1")
    new_sha = commit_file(repository, "src/BaselineOfPkg/BaselineOfPkg.class.st", "v2")

    assert baseline_changed(repository, old_sha, new_sha, "src")


def test_package_only_change_is_not_a_baseline_change(repository):
    old_sha = commit_file(repository, "src/BaselineOfPkg/BaselineOfPkg.class.st", "v1")
    new_sha = commit_file(repository, "src/Pkg/Pkg.class.st", "v1")

    assert not baseline_changed(repository, old_sha, new_sha, "src")
