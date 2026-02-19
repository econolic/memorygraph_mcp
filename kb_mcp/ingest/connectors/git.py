from __future__ import annotations

import subprocess
from pathlib import Path


class GitConnector:
    def changed_files(self, repo_root: str, since_ref: str = "HEAD~1") -> list[str]:
        cmd = ["git", "-C", repo_root, "diff", "--name-only", since_ref, "HEAD"]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            return []
        files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        return [str(Path(repo_root) / rel) for rel in files]
