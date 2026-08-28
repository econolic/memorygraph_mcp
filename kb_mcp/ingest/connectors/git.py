from __future__ import annotations

import subprocess
from pathlib import Path


class GitConnector:
    def __init__(self, *, timeout_s: float = 15.0) -> None:
        self._timeout_s = max(0.1, timeout_s)

    def changed_files(self, repo_root: str, since_ref: str = "HEAD~1") -> list[str]:
        cmd = ["git", "-C", repo_root, "diff", "--name-only", since_ref, "HEAD"]
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
        except subprocess.TimeoutExpired:
            return []
        if proc.returncode != 0:
            return []
        files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return [str(Path(repo_root) / rel) for rel in files]
