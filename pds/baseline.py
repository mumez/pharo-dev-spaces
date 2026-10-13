"""Derive a projects.json entry (packages in load order) from a repository's BaselineOf.

Same idea as the st-import skill of smalltalk-dev: collect `package:` / `requires:` / `group:`
declarations and sort the packages topologically, BaselineOf first.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_DECLARATION = re.compile(r"package:\s*'([^']+)'(?:\s*with:\s*\[(.*?)\])?", re.DOTALL)
REQUIRES_CLAUSE = re.compile(r"requires:\s*(#\(.*?\)|'[^']*')", re.DOTALL)
GROUP_DECLARATION = re.compile(r"group:\s*'([^']+)'\s*with:\s*(#\(.*?\)|'[^']*')", re.DOTALL)
NAME_IN_LITERAL = re.compile(r"'([^']+)'|([A-Za-z][\w.-]*)")
SRC_DIRECTORY = re.compile(r"'srcDirectory'\s*:\s*'([^']*)'")
DEFAULT_GROUP = "default"


def names_in_literal(literal):
    """Names in `'Foo'` or `#( 'Foo' Bar )`."""
    inner = literal[2:-1] if literal.startswith("#(") else literal
    return [quoted or bare for quoted, bare in NAME_IN_LITERAL.findall(inner)]


@dataclass
class BaselineSpec:
    name: str
    src_dir: str
    package_requirements: dict  # package name -> required package / group / external project names
    groups: dict = field(default_factory=dict)  # group name -> member package / group names

    @classmethod
    def from_repository(cls, repository):
        repository = Path(repository)
        project_file = repository / ".project"
        match = SRC_DIRECTORY.search(project_file.read_text()) if project_file.exists() else None
        src_dir = match.group(1) if match else "src"
        baseline_dirs = sorted((repository / src_dir).glob("BaselineOf*/"))
        if not baseline_dirs:
            raise FileNotFoundError(f"no BaselineOf* package under {repository / src_dir}")
        baseline_dir = baseline_dirs[0]
        source = (baseline_dir / f"{baseline_dir.name}.class.st").read_text()
        return cls(
            name=baseline_dir.name.removeprefix("BaselineOf"),
            src_dir=src_dir,
            package_requirements=parse_package_requirements(source),
            groups={name: names_in_literal(members) for name, members in GROUP_DECLARATION.findall(source)},
        )

    def expand(self, name):
        """Packages meant by a package or group name (external project names expand to nothing)."""
        if name in self.package_requirements:
            return [name]
        return [package for member in self.groups.get(name, []) for package in self.expand(member)]

    def required_packages(self, package):
        return [required for name in self.package_requirements[package] for required in self.expand(name)]

    def load_order(self, group_names):
        selected = self.packages_for_groups(group_names)
        pending = [package for package in self.package_requirements if package in selected]
        ordered = []
        while pending:
            ready = next(
                (package for package in pending if set(self.required_packages(package)) <= set(ordered)), None
            )
            if ready is None:
                raise ValueError(f"cyclic package requirements among {pending}")
            ordered.append(ready)
            pending.remove(ready)
        return [f"BaselineOf{self.name}", *ordered]

    def packages_for_groups(self, group_names):
        """Packages Metacello loads for these groups, including in-baseline requirements."""
        if group_names == [DEFAULT_GROUP] and DEFAULT_GROUP not in self.groups:
            return set(self.package_requirements)
        selected = set()
        to_visit = [package for name in group_names for package in self.expand(name)]
        while to_visit:
            package = to_visit.pop()
            if package not in selected:
                selected.add(package)
                to_visit.extend(self.required_packages(package))
        return selected


def parse_package_requirements(source):
    package_requirements = {}
    for package, with_block in PACKAGE_DECLARATION.findall(source):
        requires = REQUIRES_CLAUSE.search(with_block)
        package_requirements[package] = names_in_literal(requires.group(1)) if requires else []
    return package_requirements


def project_entry(repository, group_names=(DEFAULT_GROUP,)):
    spec = BaselineSpec.from_repository(repository)
    return {
        "repository": str(Path(repository).resolve()),
        "baseline": spec.name,
        "srcDir": spec.src_dir,
        "groups": list(group_names),
        "packages": spec.load_order(list(group_names)),
    }
