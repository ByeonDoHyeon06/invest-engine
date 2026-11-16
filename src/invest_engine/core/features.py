"""Deterministic, dependency-only feature scheduling skeleton for E4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class FeatureNode:
    name: str
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or any(not name.strip() for name in self.dependencies):
            raise ValueError("invalid feature name")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("duplicate dependencies")


class FeatureGraph:
    def __init__(self, features: Iterable[FeatureNode]) -> None:
        items = tuple(features)
        self._nodes = {feature.name: feature for feature in items}
        if len(self._nodes) != len(items):
            raise ValueError("feature graph must have unique nodes")
        for node in self._nodes.values():
            for dependency in node.dependencies:
                if dependency not in self._nodes:
                    raise ValueError(f"unknown feature dependency: {dependency}")
        self.schedule(self._nodes)

    def schedule(self, requested: Iterable[str]) -> tuple[str, ...]:
        ordered: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name not in self._nodes:
                raise ValueError(f"unknown feature: {name}")
            if name in visiting:
                raise ValueError("feature dependency cycle")
            if name in visited:
                return
            visiting.add(name)
            for dependency in sorted(self._nodes[name].dependencies):
                visit(dependency)
            visiting.remove(name)
            visited.add(name)
            ordered.append(name)

        for name in sorted(set(requested)):
            visit(name)
        return tuple(ordered)
