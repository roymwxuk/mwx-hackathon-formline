"""Agent prompts as versioned files (`<name>.md`): a small header, then the prompt text.

    ---
    name: router
    version: 1
    description: what the agent does
    changes: what each version changed
    ---
    <the prompt, sent to the model as the agent's instructions>

Prompts live apart from the code so they can be read, reviewed and changed on their own; the
JSON contracts and the verifiers that check the replies stay in code. `Prompt.ref` (name,
version and a hash of the text) names the exact prompt behind an output. The LLM response
cache keys on the full text, so changing a prompt never serves an answer written for the old
one: bump `version` and note the change in `changes`.
"""

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    description: str
    text: str

    @property
    def ref(self) -> str:
        """e.g. "router@v1+3f2a9c1d": name, version and the first 8 hex of the text's SHA-256."""
        return f"{self.name}@v{self.version}+{hashlib.sha256(self.text.encode()).hexdigest()[:8]}"


@cache
def load(name: str) -> Prompt:
    raw = (DIR / f"{name}.md").read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"prompt {name}: missing the --- header")
    header, body = raw[4:].split("\n---\n", 1)
    meta = dict(line.split(": ", 1) for line in header.splitlines() if line.strip())
    if meta.get("name") != name:
        raise ValueError(f"prompt {name}: header says {meta.get('name')!r}")
    text = body.removesuffix("\n")  # the file ends with one newline
    return Prompt(name, int(meta["version"]), meta.get("description", ""), text)
