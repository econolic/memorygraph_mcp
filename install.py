#!/usr/bin/env python3
import os
import sys
import json
import shutil
from dataclasses import dataclass
from typing import Protocol, Any, Dict, List, runtime_checkable, cast


@runtime_checkable
class ConfigFormatter(Protocol):
    """Protocol defining interface for formatting/updating MCP configuration structures."""

    def update(self, config: Any, dst_bridge_path: str) -> Any: ...


class DictConfigFormatter:
    """Formatter for dictionary-based configuration files (e.g., Cursor, Cline, Claude Desktop)."""

    def __init__(self, is_gemini: bool = False) -> None:
        self.is_gemini = is_gemini

    def update(self, config: Any, dst_bridge_path: str) -> Dict[str, Any]:
        if not isinstance(config, dict):
            config = {}
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["hybrid-kb-mcp"] = {
            "command": "python",
            "args": [dst_bridge_path.replace("\\", "/")],
            "env": {},
        }

        if self.is_gemini:
            config["mcpServers"]["hybrid-kb-mcp"][
                "$typeName"
            ] = "exa.cascade_plugins_pb.CascadePluginCommandTemplate"

        return cast(Dict[str, Any], config)


class ListConfigFormatter:
    """Formatter for list-based configuration files (e.g., Continue)."""

    def update(self, config: Any, dst_bridge_path: str) -> Dict[str, Any]:
        if not isinstance(config, dict):
            config = {}
        if "mcpServers" not in config:
            config["mcpServers"] = []

        servers = config["mcpServers"]
        if not isinstance(servers, list):
            servers = []

        # Remove existing config if any
        servers = [
            s
            for s in servers
            if isinstance(s, dict) and s.get("name") != "hybrid-kb-mcp"
        ]

        # Add new config
        servers.append(
            {
                "name": "hybrid-kb-mcp",
                "command": "python",
                "args": [dst_bridge_path.replace("\\", "/")],
            }
        )

        config["mcpServers"] = servers
        return cast(Dict[str, Any], config)


@dataclass
class IdeTarget:
    """Class representing an IDE/Plugin target configuration."""

    name: str
    config_dir: str
    config_file: str
    format_type: str = "dict"

    def get_config_path(self) -> str:
        return os.path.join(self.config_dir, self.config_file)

    def get_scratch_dir(self) -> str:
        return os.path.join(self.config_dir, "scratch")

    def get_formatter(self) -> ConfigFormatter:
        if self.format_type == "list":
            return ListConfigFormatter()
        return DictConfigFormatter(
            is_gemini="Gemini" in self.name or "Antigravity" in self.name
        )


class SystemPathResolver:
    """Responsibility: Dynamically resolve OS-specific configuration folders."""

    def __init__(self) -> None:
        self.user_home = os.path.expanduser("~")
        self.appdata = os.environ.get("APPDATA", "")

    def get_targets(self) -> List[IdeTarget]:
        if sys.platform == "win32":
            cursor_dir = os.path.join(
                self.appdata, "Cursor", "User", "globalStorage", "co.anysphere.cursor"
            )
            claude_dir = os.path.join(self.appdata, "Claude")
            cline_dir = os.path.join(
                self.appdata, "Code", "User", "globalStorage", "saoudrizwan.claude-dev"
            )
            roo_dir = os.path.join(
                self.appdata, "Code", "User", "globalStorage", "roodev.roo-cline"
            )
        elif sys.platform == "darwin":  # macOS
            cursor_dir = os.path.join(
                self.user_home,
                "Library",
                "Application Support",
                "Cursor",
                "User",
                "globalStorage",
                "co.anysphere.cursor",
            )
            claude_dir = os.path.join(
                self.user_home, "Library", "Application Support", "Claude"
            )
            cline_dir = os.path.join(
                self.user_home,
                "Library",
                "Application Support",
                "Code",
                "User",
                "globalStorage",
                "saoudrizwan.claude-dev",
            )
            roo_dir = os.path.join(
                self.user_home,
                "Library",
                "Application Support",
                "Code",
                "User",
                "globalStorage",
                "roodev.roo-cline",
            )
        else:  # Linux
            cursor_dir = os.path.join(
                self.user_home,
                ".config",
                "Cursor",
                "User",
                "globalStorage",
                "co.anysphere.cursor",
            )
            claude_dir = os.path.join(self.user_home, ".config", "Claude")
            cline_dir = os.path.join(
                self.user_home,
                ".config",
                "Code",
                "User",
                "globalStorage",
                "saoudrizwan.claude-dev",
            )
            roo_dir = os.path.join(
                self.user_home,
                ".config",
                "Code",
                "User",
                "globalStorage",
                "roodev.roo-cline",
            )

        gemini_dir = os.path.join(self.user_home, ".gemini", "antigravity-ide")
        continue_dir = os.path.join(self.user_home, ".continue")

        raw_targets = [
            {
                "name": "Antigravity IDE / Gemini",
                "dir": gemini_dir,
                "file": "mcp_config.json",
                "format": "dict",
            },
            {"name": "Cursor", "dir": cursor_dir, "file": "mcp.json", "format": "dict"},
            {
                "name": "Claude Desktop",
                "dir": claude_dir,
                "file": "claude_desktop_config.json",
                "format": "dict",
            },
            {
                "name": "VS Code (Cline)",
                "dir": cline_dir,
                "file": "settings.json",
                "format": "dict",
            },
            {
                "name": "VS Code (Roo Code)",
                "dir": roo_dir,
                "file": "settings.json",
                "format": "dict",
            },
            {
                "name": "Continue Plugin (VS Code/PyCharm)",
                "dir": continue_dir,
                "file": "config.json",
                "format": "list",
            },
        ]

        targets = []
        for t in raw_targets:
            # Only instantiate and validate targets that exist on the machine
            if os.path.exists(t["dir"]):
                targets.append(
                    IdeTarget(
                        name=t["name"],
                        config_dir=t["dir"],
                        config_file=t["file"],
                        format_type=t["format"],
                    )
                )
        return targets


class BridgeInstaller:
    """Responsibility: Coordinate copying bridge files and updating configuration files."""

    def __init__(self, repo_root: str) -> None:
        self.repo_root = repo_root

    def install_to(self, target: IdeTarget) -> bool:
        print(f"\nInstalling to {target.name}...")
        scratch_dir = target.get_scratch_dir()

        try:
            os.makedirs(scratch_dir, exist_ok=True)
        except Exception as e:
            sys.stderr.write(f"  [-] Failed to create scratch directory: {e}\n")
            return False

        # 1. Save repository root path
        path_file = os.path.join(scratch_dir, "mcp_repo_path.txt")
        try:
            with open(path_file, "w", encoding="utf-8") as f:
                f.write(self.repo_root)
            print(f"  [+] Saved repository path to: {path_file}")
        except Exception as e:
            sys.stderr.write(f"  [-] Failed to save repository path: {e}\n")
            return False

        # 2. Copy bridge script
        src_bridge = os.path.join(self.repo_root, "scripts", "mcp_docker_bridge.py")
        dst_bridge = os.path.join(scratch_dir, "mcp_docker_bridge.py")
        try:
            shutil.copy2(src_bridge, dst_bridge)
            print(f"  [+] Copied bridge script to: {dst_bridge}")
        except Exception as e:
            sys.stderr.write(f"  [-] Failed to copy bridge script: {e}\n")
            return False

        # 3. Read, update, and write the IDE configuration file
        config_path = target.get_config_path()
        config_content = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_content = json.load(f)
            except Exception as e:
                sys.stderr.write(
                    f"  [!] Warning: failed to parse existing config {config_path}: {e}. Creating new.\n"
                )

        formatter = target.get_formatter()
        updated_config = formatter.update(config_content, dst_bridge)

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(updated_config, f, indent=2)
            print(f"  [+] Registered server in: {target.config_file}")
            return True
        except Exception as e:
            sys.stderr.write(f"  [-] Failed to write config file {config_path}: {e}\n")
            return False


def main() -> None:
    repo_root = os.path.dirname(os.path.abspath(__file__))
    print("==================================================")
    print("Starting MCP Bridge Installation")
    print(f"Repository Root: {repo_root}")
    print("==================================================")

    resolver = SystemPathResolver()
    targets = resolver.get_targets()

    if not targets:
        print("No supported IDE or plugin configurations detected automatically.")
        print("To configure manually, add 'hybrid-kb-mcp' pointing to:")
        manual_path = os.path.join(
            repo_root, "scripts", "mcp_docker_bridge.py"
        ).replace("\\", "/")
        print(f"  {manual_path}")
        print("==================================================")
        return

    installer = BridgeInstaller(repo_root)
    success_count = 0

    for target in targets:
        if installer.install_to(target):
            success_count += 1

    print("\n" + "=" * 50)
    if success_count > 0:
        print(f"Installation finished successfully for {success_count} targets!")
    else:
        print("Installation failed.")
    print("=" * 50)


if __name__ == "__main__":
    main()
