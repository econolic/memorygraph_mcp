from __future__ import annotations

from pathlib import Path


class FilesystemConnector:
    def read_documents(
        self,
        root: str,
        allowed_ext: tuple[str, ...] = (".md", ".txt", ".py", ".sql"),
        include_paths: set[str] | None = None,
    ) -> list[dict[str, object]]:
        docs: list[dict[str, object]] = []
        base = Path(root)
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in allowed_ext:
                continue
            abs_path = str(path.resolve())
            if include_paths is not None and abs_path not in include_paths:
                continue
            rel_path = str(path.relative_to(base))
            suffix = path.suffix.lower().lstrip(".")
            docs.append(
                {
                    "source_path": abs_path,
                    "title": path.name,
                    "source": rel_path,
                    "tags": [f"ext:{suffix}"] if suffix else [],
                    "text": path.read_text(encoding="utf-8", errors="ignore"),
                }
            )
        return docs
