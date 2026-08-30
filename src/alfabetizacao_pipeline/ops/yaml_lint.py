import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn, override

REQUIRED_PATHS: Final = (".github", "cloudbuild", "ops")
OPTIONAL_PATHS: Final = ("workflows",)
YAMLLINT_VERSION: Final = "yamllint==1.37.1"


@dataclass(frozen=True, slots=True)
class MissingYamlPathError(Exception):
    """Raised when a required YAML configuration directory is absent."""

    path: Path

    @override
    def __str__(self) -> str:
        return f"required YAML path not found: {self.path}"


def select_yaml_paths(root: Path) -> tuple[Path, ...]:
    """Select required directories and an optional integrated workflows directory."""
    required = tuple(root / name for name in REQUIRED_PATHS)
    for path in required:
        if not path.is_dir():
            raise MissingYamlPathError(path=path)
    optional = tuple(root / name for name in OPTIONAL_PATHS if (root / name).is_dir())
    return (*required, *optional)


def run_yaml_lint(root: Path) -> int:
    """Run the pinned linter against every currently applicable YAML surface."""
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
    """Exit with yamllint's exact process outcome for CI consumption."""
    raise SystemExit(run_yaml_lint(Path.cwd()))


if __name__ == "__main__":
    main()
