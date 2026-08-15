from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class TraceEntry:
    # "llm" | "tool_call" | "tool_result" | "error"
    kind: str
    iteration: int
    data: dict


@dataclass
class Trace:
    entries: list[TraceEntry] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            [
                {"kind": e.kind, "iteration": e.iteration, "data": e.data}
                for e in self.entries
            ],
            ensure_ascii=False,
            default=str,
        )
