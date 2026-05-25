"""Adapter between AI Brother features and the upstream nanobot runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from aibrother.cards import AIBrotherCardKind

if TYPE_CHECKING:
    from nanobot import Nanobot, RunResult


@dataclass(slots=True)
class AIBrotherRuntime:
    """Project-specific facade that keeps nanobot behind one boundary."""

    bot: Nanobot

    @classmethod
    def from_nanobot_config(
        cls,
        config_path: str | Path | None = None,
        *,
        workspace: str | Path | None = None,
    ) -> AIBrotherRuntime:
        from nanobot import Nanobot

        return cls(Nanobot.from_config(config_path, workspace=workspace))

    async def run_feature(
        self,
        feature: AIBrotherCardKind,
        message: str,
        *,
        session_key: str | None = None,
    ) -> RunResult:
        """Run one AI Brother feature through nanobot using isolated sessions."""

        key = session_key or f"aibrother:{feature}:default"
        return await self.bot.run(message, session_key=key)
