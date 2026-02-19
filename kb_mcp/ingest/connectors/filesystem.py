from __future__ import annotations

from pathlib import Path


class FilesystemConnector:
    def read_documents(self, root: str, allowed_ext: tuple[str, ...] = (".md", ".txt", ".py", ".sql")) -> list[dict[str, str]]:
        docs: list[dict[str, str]] = []
        base = Path(root)
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in allowed_ext:
                continue
            docs.append(
                {
                    "source_path": str(path),
                    "title": path.name,
                    "text": path.read_text(encoding="utf-8", errors="ignore"),
                }
            )
        return docs
