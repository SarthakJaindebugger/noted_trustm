"""
PromptManager — loads prompts from config.yaml and fills template variables at runtime.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    """Loads prompt templates from the parsed config and renders them with variables."""

    def __init__(self, prompts_config: Dict[str, Any]):
        self._prompts = prompts_config

    def get_raw(self, prompt_path: str) -> Optional[str]:
        """Get a raw (unfilled) prompt template by dotted path, e.g. 'live_summary.system'."""
        parts = prompt_path.split(".")
        node: Any = self._prompts
        for part in parts:
            if isinstance(node, dict):
                node = node.get(part)
            else:
                return None
        return node if isinstance(node, str) else None

    def render(self, prompt_path: str, **kwargs: Any) -> str:
        """Render a prompt template with keyword arguments.

        Unresolved placeholders are left as-is so partial rendering is safe.
        """
        template = self.get_raw(prompt_path)
        if template is None:
            logger.warning("Prompt template not found: %s", prompt_path)
            return ""
        try:
            return template.format(**kwargs)
        except KeyError as exc:
            logger.warning("Missing variable %s in prompt '%s', leaving placeholder", exc, prompt_path)
            # Partial render: fill what we can, leave the rest
            import re
            result = template
            for key, value in kwargs.items():
                result = result.replace("{" + key + "}", str(value))
            return result

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get an entire prompt section as a dict, e.g. 'experiment'."""
        node = self._prompts.get(section, {})
        return node if isinstance(node, dict) else {}

    def list_prompts(self) -> list[str]:
        """List all top-level prompt sections."""
        return list(self._prompts.keys())
