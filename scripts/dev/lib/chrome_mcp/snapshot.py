"""Parse semantic nodes from Chrome DevTools MCP accessibility snapshots."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_NODE_RE = re.compile(
    r'^\s*uid=(\S+)\s+(\S+)(?:\s+"((?:\\.|[^"])*)")?(.*)$'
)


class SnapshotLookupError(RuntimeError):
    """Raised when a semantic target is missing or ambiguous."""


@dataclass(frozen=True, slots=True)
class SnapshotNode:
    uid: str
    role: str
    name: str
    attributes: str

    @property
    def disabled(self) -> bool:
        return " disabled" in f" {self.attributes}"


def _decode_name(value: str | None) -> str:
    if value is None:
        return ""
    try:
        decoded = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value
    return decoded if isinstance(decoded, str) else value


@dataclass(frozen=True, slots=True)
class McpSnapshot:
    text: str
    nodes: tuple[SnapshotNode, ...]

    @classmethod
    def parse(cls, text: str) -> McpSnapshot:
        nodes: list[SnapshotNode] = []
        for line in text.splitlines():
            match = _NODE_RE.match(line)
            if match is None:
                continue
            uid, role, encoded_name, attributes = match.groups()
            nodes.append(
                SnapshotNode(
                    uid=uid,
                    role=role,
                    name=_decode_name(encoded_name),
                    attributes=attributes.strip(),
                )
            )
        return cls(text=text, nodes=tuple(nodes))

    def find(
        self,
        role: str,
        name: str | tuple[str, ...],
        *,
        exact: bool = True,
        enabled: bool = True,
    ) -> SnapshotNode:
        names = (name,) if isinstance(name, str) else name
        matches = [
            node
            for node in self.nodes
            if node.role == role
            and (not enabled or not node.disabled)
            and any(
                node.name == candidate if exact else candidate in node.name
                for candidate in names
            )
        ]
        if len(matches) == 1:
            return matches[0]
        available = [
            node.name for node in self.nodes if node.role == role and node.name
        ]
        if not matches:
            raise SnapshotLookupError(
                f"MCP UI target missing: role={role!r} name={names!r}; "
                f"available={available[:20]!r}"
            )
        raise SnapshotLookupError(
            f"MCP UI target ambiguous: role={role!r} name={names!r}; "
            f"matches={[node.name for node in matches]!r}"
        )

