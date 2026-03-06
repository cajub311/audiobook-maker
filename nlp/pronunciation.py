from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


class PronunciationDict:
    def __init__(self, overrides: Optional[dict[str, str]] = None):
        self.overrides = overrides or {}

    def apply(self, text: str) -> str:
        output = text
        for word, replacement in self.overrides.items():
            pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
            output = pattern.sub(replacement, output)
        return output

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.overrides, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path) -> "PronunciationDict":
        with open(path, "r", encoding="utf-8") as f:
            return cls(json.load(f))
