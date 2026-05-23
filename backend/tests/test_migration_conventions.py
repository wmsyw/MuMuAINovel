from __future__ import annotations

# pyright: reportAny=false, reportExplicitAny=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnusedCallResult=false

import ast
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_TREES = {
    "postgres": BACKEND_ROOT / "alembic/postgres/versions",
    "sqlite": BACKEND_ROOT / "alembic/sqlite/versions",
}


def _migration_files(tree_path: Path) -> list[Path]:
    return sorted(path for path in tree_path.glob("*.py") if path.name != "__init__.py")


def _extract_assignment(module: ast.Module, name: str) -> Any:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            if node.value is None:
                return None
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")


def _load_migration_metadata(path: Path) -> tuple[str, object, str]:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    revision = str(_extract_assignment(module, "revision"))
    down_revision = _extract_assignment(module, "down_revision")
    return revision, down_revision, source


def _collect_tree_metadata(tree_name: str) -> tuple[list[Path], dict[str, object], dict[str, str], dict[str, set[str]]]:
    files = _migration_files(MIGRATION_TREES[tree_name])
    down_revisions: dict[str, object] = {}
    sources: dict[str, str] = {}
    parents: dict[str, set[str]] = {}

    for path in files:
        revision, down_revision, source = _load_migration_metadata(path)
        down_revisions[revision] = down_revision
        sources[revision] = source
        parents.setdefault(revision, set())

        if isinstance(down_revision, tuple):
            for parent in down_revision:
                parents.setdefault(str(parent), set()).add(revision)
        elif down_revision is not None:
            parents.setdefault(str(down_revision), set()).add(revision)

    return files, down_revisions, sources, parents


def _flatten_down_revisions(down_revision: object) -> tuple[str, ...]:
    if down_revision is None:
        return ()
    if isinstance(down_revision, tuple):
        return tuple(str(item) for item in down_revision)
    return (str(down_revision),)


def _assert_tree_conventions(tree_name: str) -> None:
    files, down_revisions, sources, parents = _collect_tree_metadata(tree_name)
    revisions = set(down_revisions)

    assert files, f"{tree_name} tree must contain migrations"

    for revision, down_revision in down_revisions.items():
        source = sources[revision]
        assert "def upgrade()" in source, f"{tree_name}:{revision} missing upgrade()"
        assert "def downgrade()" in source, f"{tree_name}:{revision} missing downgrade()"
        for parent_revision in _flatten_down_revisions(down_revision):
            assert parent_revision in revisions, f"{tree_name}:{revision} references missing parent {parent_revision}"

    heads = sorted(revision for revision in revisions if not parents.get(revision))
    assert len(heads) == 1, f"{tree_name} tree should resolve to a single head, found {heads}"

    roots = sorted(revision for revision, down_revision in down_revisions.items() if not _flatten_down_revisions(down_revision))
    assert len(roots) == 1, f"{tree_name} tree should have a single root, found {roots}"

    reachable = set()

    def visit(revision: str) -> None:
        if revision in reachable:
            return
        reachable.add(revision)
        for parent_revision in _flatten_down_revisions(down_revisions[revision]):
            visit(parent_revision)

    visit(heads[0])
    assert reachable == revisions, f"{tree_name} tree has disconnected migration revisions: {sorted(revisions - reachable)}"


def test_postgres_and_sqlite_migration_trees_follow_same_conventions() -> None:
    postgres_files = _migration_files(MIGRATION_TREES["postgres"])
    sqlite_files = _migration_files(MIGRATION_TREES["sqlite"])

    assert len(postgres_files) == len(sqlite_files), (
        f"postgres and sqlite migration file counts must match: "
        f"{len(postgres_files)} != {len(sqlite_files)}"
    )

    _assert_tree_conventions("postgres")
    _assert_tree_conventions("sqlite")
