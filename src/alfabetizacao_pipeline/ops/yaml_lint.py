import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn, override

REQUIRED_PATHS: Final = (".github", "cloudbuild", "ops")
OPTIONAL_PATHS: Final = ("workflows",)
YAMLLINT_VERSION: Final = "yamllint==1.37.1"


@dataclass(frozen=True, slots=True)
class MissingYamlPathError(Exception):
    """Carry the missing configuration path without parsing an error message."""

    path: Path

    @override
    def __str__(self) -> str:
        return f"required YAML path not found: {self.path}"


def select_yaml_paths(root: Path) -> tuple[Path, ...]:
    """Require core configuration roots while accepting the workflow extension."""
    required = tuple(root / name for name in REQUIRED_PATHS)
    for path in required:
        if not path.is_dir():
            raise MissingYamlPathError(path=path)
    optional = tuple(root / name for name in OPTIONAL_PATHS if (root / name).is_dir())
    return (*required, *optional)


def run_yaml_lint(root: Path) -> int:
    """Invoke the pinned linter only with repository-derived arguments."""
    config_path = root / ".yamllint.yml"
    paths = select_yaml_paths(root)
    command = (
        "uvx",
        "--from",
        YAMLLINT_VERSION,
        "yamllint",
        "--config-file",
        str(config_path),
        *(str(path) for path in paths),
    )
    # The command prefix and arguments are assembled only from repository constants.
    result = subprocess.run(command, cwd=root, check=False)  # noqa: S603
    return result.returncode


def main() -> NoReturn:
    """Propagate yamllint's exact process outcome to CI."""
    raise SystemExit(run_yaml_lint(Path.cwd()))


if __name__ == "__main__":
    main()
