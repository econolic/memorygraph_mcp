#!/usr/bin/env python3
import sys
import os
import subprocess


def load_env(env_path: str) -> dict[str, str]:
    """Simple parser for .env file to avoid external dependencies like python-dotenv."""
    env_vars: dict[str, str] = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        # strip quotes if present
                        val = val.strip().strip("'\"")
                        env_vars[key.strip()] = val
        except Exception as e:
            sys.stderr.write(f"Warning: could not read .env file: {e}\n")
    return env_vars


def main() -> None:
    # 1. Determine active workspace path on the host
    workspace_path = os.getcwd()
    workspace_id = os.path.basename(workspace_path)

    # 2. Locate the repository path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_path_file = os.path.join(script_dir, "mcp_repo_path.txt")

    repo_root = ""
    # If the path settings file exists in the same directory, read from it
    if os.path.exists(repo_path_file):
        try:
            with open(repo_path_file, "r", encoding="utf-8") as f:
                repo_root = f.read().strip()
        except Exception:
            pass

    # Fallback to resolving relative to the script location (assuming scripts/ folder inside repo)
    if not repo_root or not os.path.exists(repo_root):
        repo_root = os.path.dirname(script_dir)

    env_path = os.path.join(repo_root, ".env")

    # 3. Load variables from .env file
    env_vars = load_env(env_path)

    # 4. Determine docker network name dynamically
    project_name = env_vars.get("COMPOSE_PROJECT_NAME") or os.path.basename(repo_root)
    project_name = "".join(c for c in project_name if c.isalnum() or c == "_").lower()
    network_name = f"{project_name}_default"

    # 5. Set default environment parameters
    defaults = {
        "KB_QDRANT_URL": "http://qdrant:6333",
        "KB_NEO4J_URI": "bolt://neo4j:7687",
        "KB_NEO4J_USER": "neo4j",
        "KB_NEO4J_PASSWORD": "neo4jpass",
        "KB_NEO4J_DATABASE": "neo4j",
        "KB_EMBEDDING_PROVIDER": "local",
        "KB_EMBEDDING_MODEL": "sentence-transformers/all-MiniLM-L6-v2",
        "KB_EMBEDDING_DIMENSIONS": "384",
        "KB_AUTO_INGEST_ENABLED": "true",
        "KB_AUTO_INGEST_INTERVAL_S": "900",
        "KB_AUTO_INGEST_RUN_ON_START": "true",
    }

    # Gather variables, prioritizing: host environment -> .env file -> defaults
    effective_env = {}
    for key, def_val in defaults.items():
        val = os.environ.get(key) or env_vars.get(key) or def_val
        effective_env[key] = val

    # Also forward any other KB_ or NEO4J_ variables found in .env
    for key, val in env_vars.items():
        if key.startswith("KB_") or key.startswith("NEO4J_"):
            if key not in effective_env:
                effective_env[key] = val

    # 6. Define docker run command to launch stdio transport
    cmd = [
        "docker",
        "run",
        "-i",
        "--rm",
        "-a",
        "stdin",
        "-a",
        "stdout",
        "-a",
        "stderr",
        "--network",
        network_name,
        "-v",
        f"{workspace_path}:/workspace",
        "-e",
        "PYTHONUNBUFFERED=1",
        "-e",
        "KB_AUTO_INGEST_ROOTS=/workspace",
        "-e",
        "KB_INGEST_ALLOWED_ROOTS=/workspace",
        "-e",
        f"KB_AUTO_INGEST_WORKSPACE_ID={workspace_id}",
    ]

    # Append all resolved environment variables
    for key, val in effective_env.items():
        cmd.extend(["-e", f"{key}={val}"])

    cmd.extend(
        ["memorygraph_mcp-mcp:latest", "python", "-m", "kb_mcp.server.transport_stdio"]
    )

    # 7. Pipe stdio directly to the docker container process
    try:
        sys.exit(subprocess.call(cmd))
    except Exception as e:
        sys.stderr.write(f"Failed to spawn Docker MCP container: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
