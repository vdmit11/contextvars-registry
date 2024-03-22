import os.path
from doit.tools import Interactive
from typing import List, Iterable

DOIT_CONFIG = {
    "default_tasks": [
        "lint",
        "test_multi",
    ]
}


SRC_DIRS = [
    "contextvars_registry",
    "tests",
    "docs",
]


def _find_src_files(src_dirs: Iterable[str]) -> List[str]:
    # Find .py/.pyi/.rst/etc (files that may contain Python code).
    # Needed for watching the files and auto-running tasks on change (using doit auto).
    def _is_src_file(directory: str, filename: str) -> bool:
        return (
            (
                filename.endswith(".py")
                or filename.endswith(".pyi")
                or filename.endswith(".rst")
            )
            and not filename.startswith(".")
            and not directory.startswith(".")
        )

    return [
        os.path.join(directory, filename)
        for src_dir in SRC_DIRS
        for directory, _, filenames in os.walk(src_dir)
        for filename in filenames
        if _is_src_file(directory, filename)
    ]


SRC_FILES = _find_src_files(SRC_DIRS)

# whitespace-separated lists, needed for composing shell commands
SRC_FILES_STR = " ".join(SRC_FILES)
SRC_DIRS_STR = " ".join(SRC_DIRS)


def task_fix():
    return {
        "file_dep": SRC_FILES,
        "actions": [
            Interactive("ruff format {SRC_DIRS_STR}"),
            Interactive(f"ruff check --fix {SRC_DIRS_STR}"),
        ],
    }


def task_lint():
    return {
        "file_dep": SRC_FILES,
        "actions": [
            Interactive(f"ruff check {SRC_DIRS_STR}"),
            Interactive(f"mypy {SRC_DIRS_STR}"),
        ],
    }


def task_test():
    return {
        "file_dep": SRC_FILES,
        "actions": [
            Interactive(
                f"pytest --cov=contextvars_registry --cov-fail-under=100 {SRC_DIRS_STR}"
            ),
        ],
    }


def task_test_multi():
    return {
        "file_dep": SRC_FILES,
        "actions": [
            Interactive("tox -p -r"),
        ],
    }


def task_docs():
    return {
        "file_dep": SRC_FILES,
        "actions": [
            Interactive("sphinx-build docs docs/_build"),
        ],
    }
