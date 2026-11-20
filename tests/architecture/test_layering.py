"""Shared layers must stay independent of aircraft type [M§1]."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "physimesh"
RULES = {"solver": {"drone", "api"}, "postpro": {"drone", "api"},
         "core": {"drone", "solver", "postpro", "api"}}


def _resolved_imports(path: pathlib.Path):
    pkg = ["physimesh"] + list(path.relative_to(ROOT).parent.parts)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")
        elif isinstance(node, ast.ImportFrom):
            base = pkg[: len(pkg) - (node.level - 1)] if node.level else []
            mod = node.module.split(".") if node.module else []
            full = base + mod if node.level else mod
            yield full
            for a in node.names:
                yield full + [a.name]


def test_layering_rules():
    offenders = []
    for layer, forbidden in RULES.items():
        for f in (ROOT / layer).rglob("*.py"):
            for parts in _resolved_imports(f):
                if parts[:1] == ["physimesh"] and len(parts) > 1 and parts[1] in forbidden:
                    offenders.append(f"{f.relative_to(ROOT)} -> {'.'.join(parts)}")
    assert not offenders, offenders
