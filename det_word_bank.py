import json
from pathlib import Path


DEFAULT_DET_CACHE = Path("det-read-and-select-questions.json")


def load_det_overrides(path: Path = DEFAULT_DET_CACHE) -> dict[str, bool]:
    if not path.exists():
        return {}

    rows = json.loads(path.read_text(encoding="utf-8"))
    overrides: dict[str, bool] = {}
    conflicts: dict[str, set[bool]] = {}

    for row in rows:
        word = str(row.get("word") or "").strip().lower()
        if not word:
            continue
        answer = int(row.get("correct") or 0) == 1
        if word in overrides and overrides[word] != answer:
            conflicts.setdefault(word, {overrides[word]}).add(answer)
            continue
        overrides[word] = answer

    if conflicts:
        examples = ", ".join(sorted(conflicts)[:10])
        raise ValueError(f"DET word-bank answer conflicts: {examples}")

    return overrides
