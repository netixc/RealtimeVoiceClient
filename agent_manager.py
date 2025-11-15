#!/usr/bin/env python3
"""
Agent Manager - Unified agent orchestration system
Manages Claude Code, Gemini Browser, and Agent Zero agents
"""

import json
import threading
import subprocess
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging


class AgentManager:
    """Manages multiple AI agent types with registry persistence"""

    def __init__(self, working_dir: str = None, logger=None):
        """Initialize agent manager with working directory"""
        self.logger = logger or logging.getLogger("AgentManager")

        # Set working directory
        if working_dir:
            self.working_dir = Path(working_dir)
        else:
            self.working_dir = Path.cwd() / "workspace"

        self.working_dir.mkdir(parents=True, exist_ok=True)

        # Agent base directory
        self.agents_dir = self.working_dir / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)

        # Registry paths for each agent type
        self.registries = {
            "claude_code": self.agents_dir / "claude_code" / "registry.json",
            "gemini": self.agents_dir / "gemini" / "registry.json",
            "agent_zero": self.agents_dir / "agent_zero" / "registry.json"
        }

        # Create registry directories
        for registry_path in self.registries.values():
            registry_path.parent.mkdir(parents=True, exist_ok=True)

        # Thread safety
        self.registry_lock = threading.Lock()

        # Load all registries
        self.agent_data = {
            "claude_code": self._load_registry("claude_code"),
            "gemini": self._load_registry("gemini"),
            "agent_zero": self._load_registry("agent_zero")
        }

        # Background threads for async agent execution
        self.background_threads: List[threading.Thread] = []

        # Find Claude CLI
        self.claude_cli_path = self._find_claude_cli()

        self.logger.info(f"AgentManager initialized with working_dir: {self.working_dir}")
        self.logger.info(f"Claude CLI path: {self.claude_cli_path}")

    # ------------------------------------------------------------------ #
    # Registry Management
    # ------------------------------------------------------------------ #

    def _load_registry(self, tool: str) -> Dict[str, Any]:
        """Load agent registry from disk"""
        registry_path = self.registries.get(tool)
        if not registry_path or not registry_path.exists():
            return {"agents": {}}

        try:
            with registry_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if "agents" not in data:
                    data["agents"] = {}
                return data
        except Exception as e:
            self.logger.error(f"Failed to load {tool} registry: {e}")
            return {"agents": {}}

    def _save_registry(self, tool: str):
        """Save agent registry to disk"""
        registry_path = self.registries.get(tool)
        if not registry_path:
            return

        try:
            with registry_path.open("w", encoding="utf-8") as f:
                json.dump(self.agent_data[tool], f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save {tool} registry: {e}")

    def _register_agent(self, tool: str, agent_name: str, metadata: Dict[str, Any]):
        """Register an agent in the registry"""
        with self.registry_lock:
            self.agent_data[tool].setdefault("agents", {})[agent_name] = metadata
            self._save_registry(tool)

    def _get_agent(self, agent_name: str) -> Optional[tuple[str, Dict[str, Any]]]:
        """Get agent metadata by name (searches all registries)"""
        with self.registry_lock:
            for tool, data in self.agent_data.items():
                if agent_name in data.get("agents", {}):
                    return (tool, data["agents"][agent_name])
        return None

    def _delete_agent_from_registry(self, tool: str, agent_name: str):
        """Remove agent from registry"""
        with self.registry_lock:
            if agent_name in self.agent_data[tool].get("agents", {}):
                del self.agent_data[tool]["agents"][agent_name]
                self._save_registry(tool)

    # ------------------------------------------------------------------ #
    # Claude CLI Helper
    # ------------------------------------------------------------------ #

    def _find_claude_cli(self) -> str:
        """Find Claude CLI executable"""
        # Try local install path
        home_path = Path.home() / ".claude" / "local" / "claude"
        if home_path.exists():
            return str(home_path)

        # Check if 'claude' is in PATH
        if shutil.which("claude"):
            return "claude"

        self.logger.warning("Claude CLI not found in system PATH")
        return "claude"  # Fallback, will error if not found

    # ------------------------------------------------------------------ #
    # Public API - Agent CRUD
    # ------------------------------------------------------------------ #

    def create_agent(
        self,
        tool: str,
        agent_type: str,
        agent_name: str,
        lifetime_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Create a new agent

        Args:
            tool: Agent tool type (claude_code, gemini, agent_zero)
            agent_type: Agent type (agentic_coding, agentic_browsing, etc)
            agent_name: Unique agent name
            lifetime_hours: How long agent should live

        Returns:
            {"ok": True/False, "agent_name": str, "error": str}
        """
        # Validate tool
        if tool not in self.registries:
            return {
                "ok": False,
                "error": f"Unknown tool '{tool}'. Supported: {list(self.registries.keys())}"
            }

        # Check if agent already exists
        existing = self._get_agent(agent_name)
        if existing:
            return {
                "ok": False,
                "error": f"Agent '{agent_name}' already exists"
            }

        # Create agent metadata
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=lifetime_hours)

        metadata = {
            "tool": tool,
            "type": agent_type,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "lifetime_hours": lifetime_hours,
            "working_dir": str(self.working_dir),
            "status": "active",
            "operator_files": []
        }

        # Create agent directory
        agent_dir = self.agents_dir / tool / agent_name
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Register agent
        self._register_agent(tool, agent_name, metadata)

        self.logger.info(f"Created {tool} agent: {agent_name}")

        return {
            "ok": True,
            "agent_name": agent_name,
            "tool": tool,
            "type": agent_type,
            "working_dir": str(self.working_dir)
        }

    def list_agents(self) -> Dict[str, Any]:
        """
        List all active agents

        Returns:
            {"ok": True, "agents": [...]}
        """
        agents_list = []

        with self.registry_lock:
            for tool, data in self.agent_data.items():
                for agent_name, metadata in data.get("agents", {}).items():
                    agents_list.append({
                        "name": agent_name,
                        "tool": tool,
                        "type": metadata.get("type"),
                        "status": metadata.get("status"),
                        "created_at": metadata.get("created_at"),
                        "expires_at": metadata.get("expires_at"),
                        "operator_files": metadata.get("operator_files", [])
                    })

        return {
            "ok": True,
            "agents": agents_list,
            "count": len(agents_list)
        }

    def delete_agent(self, agent_name: str) -> Dict[str, Any]:
        """
        Delete an agent

        Args:
            agent_name: Agent to delete

        Returns:
            {"ok": True/False, "error": str}
        """
        result = self._get_agent(agent_name)
        if not result:
            return {
                "ok": False,
                "error": f"Agent '{agent_name}' not found"
            }

        tool, metadata = result

        # Delete agent directory
        agent_dir = self.agents_dir / tool / agent_name
        if agent_dir.exists():
            try:
                shutil.rmtree(agent_dir)
            except Exception as e:
                self.logger.error(f"Failed to delete agent directory: {e}")

        # Remove from registry
        self._delete_agent_from_registry(tool, agent_name)

        self.logger.info(f"Deleted agent: {agent_name}")

        return {
            "ok": True,
            "agent_name": agent_name
        }

    def get_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """
        Get detailed status of an agent

        Args:
            agent_name: Agent to query

        Returns:
            {"ok": True/False, "status": dict, "error": str}
        """
        result = self._get_agent(agent_name)
        if not result:
            return {
                "ok": False,
                "error": f"Agent '{agent_name}' not found"
            }

        tool, metadata = result

        return {
            "ok": True,
            "agent_name": agent_name,
            "tool": tool,
            "metadata": metadata
        }

    # ------------------------------------------------------------------ #
    # Agent Command Execution
    # ------------------------------------------------------------------ #

    def command_agent(self, agent_name: str, prompt: str) -> Dict[str, Any]:
        """
        Send command to an agent

        Args:
            agent_name: Agent to command
            prompt: Command/instruction for agent

        Returns:
            {"ok": True/False, "operator_file": str, "error": str}
        """
        result = self._get_agent(agent_name)
        if not result:
            return {
                "ok": False,
                "error": f"Agent '{agent_name}' not found"
            }

        tool, metadata = result

        # Route to appropriate handler
        if tool == "claude_code":
            return self._command_claude_code(agent_name, prompt, metadata)
        elif tool == "gemini":
            return self._command_gemini(agent_name, prompt, metadata)
        elif tool == "agent_zero":
            return self._command_agent_zero(agent_name, prompt, metadata)
        else:
            return {
                "ok": False,
                "error": f"Unknown tool type: {tool}"
            }

    def _command_claude_code(
        self, agent_name: str, prompt: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute Claude Code agent command"""
        # Create operator file
        agent_dir = self.agents_dir / "claude_code" / agent_name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        operator_file = f"operator_{timestamp}.md"
        operator_path = agent_dir / operator_file

        # Write operator file
        try:
            operator_path.write_text(
                f"# Operator Log: {agent_name}\n"
                f"Created: {datetime.now().isoformat()}\n\n"
                f"## Prompt\n{prompt}\n\n"
                f"## Status\nPending...\n",
                encoding="utf-8"
            )
        except Exception as e:
            return {"ok": False, "error": f"Failed to create operator file: {e}"}

        # Update registry with operator file
        with self.registry_lock:
            metadata["operator_files"].append(operator_file)
            self._save_registry("claude_code")

        # Execute in background thread
        thread = threading.Thread(
            target=self._run_claude_cli_command,
            args=(agent_name, prompt, operator_path),
            daemon=True
        )
        thread.start()
        self.background_threads.append(thread)

        return {
            "ok": True,
            "operator_file": operator_file,
            "message": f"Command dispatched to {agent_name}"
        }

    def _run_claude_cli_command(
        self, agent_name: str, prompt: str, operator_path: Path
    ):
        """Background thread to run Claude CLI command"""
        try:
            # Execute Claude CLI
            result = subprocess.run(
                [self.claude_cli_path, "--dangerously-skip-permissions", "-p", prompt],
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout
            )

            # Update operator file with result
            status_text = "✅ SUCCESS" if result.returncode == 0 else "❌ FAILED"

            operator_path.write_text(
                f"{operator_path.read_text()}\n\n"
                f"## Result\nStatus: {status_text}\n"
                f"Exit Code: {result.returncode}\n\n"
                f"### Output\n```\n{result.stdout}\n```\n\n"
                f"### Errors\n```\n{result.stderr}\n```\n",
                encoding="utf-8"
            )

            self.logger.info(f"Claude CLI command completed for {agent_name}")

        except subprocess.TimeoutExpired:
            operator_path.write_text(
                f"{operator_path.read_text()}\n\n"
                f"## Result\n❌ TIMEOUT - Command exceeded 30 minutes\n",
                encoding="utf-8"
            )
            self.logger.error(f"Claude CLI command timed out for {agent_name}")

        except Exception as e:
            operator_path.write_text(
                f"{operator_path.read_text()}\n\n"
                f"## Result\n❌ ERROR: {e}\n",
                encoding="utf-8"
            )
            self.logger.error(f"Claude CLI command failed for {agent_name}: {e}")

    def _command_gemini(
        self, agent_name: str, prompt: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute Gemini browser agent command"""
        # Placeholder for Gemini browser automation
        return {
            "ok": False,
            "error": "Gemini browser automation not yet implemented"
        }

    def _command_agent_zero(
        self, agent_name: str, prompt: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute Agent Zero command"""
        # Placeholder for Agent Zero
        return {
            "ok": False,
            "error": "Agent Zero not yet implemented"
        }

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #

    def cleanup_expired_agents(self) -> int:
        """Remove expired agents, returns count of deleted agents"""
        now = datetime.now(timezone.utc)
        deleted_count = 0

        with self.registry_lock:
            for tool, data in self.agent_data.items():
                to_delete = []
                for agent_name, metadata in data.get("agents", {}).items():
                    expires_at = datetime.fromisoformat(metadata.get("expires_at"))
                    if now > expires_at:
                        to_delete.append(agent_name)

                # Delete expired agents
                for agent_name in to_delete:
                    self.delete_agent(agent_name)
                    deleted_count += 1

        if deleted_count > 0:
            self.logger.info(f"Cleaned up {deleted_count} expired agents")

        return deleted_count
