"""AI Provider 基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.ai_capabilities import ReasoningConfig
from app.services.json_helper import parse_json


@dataclass(frozen=True)
class AICapabilities:
    """Provider feature flags used by orchestration and plugin discovery."""

    text: bool = True
    streaming: bool = True
    structured: bool = True
    tools: bool = False
    reasoning: bool = False


class BaseAIProvider(ABC):
    """AI 提供商抽象基类"""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ) -> Dict[str, Any]:
        """Generate a normalized provider response with content and usage metadata."""
        raise NotImplementedError

    async def generate_text(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ) -> str:
        """Generate plain text while preserving the normalized low-level contract."""
        response = await self.generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_config=reasoning_config,
        )
        content = response.get("content")
        return "" if content is None else str(content)

    async def generate_structured(
        self,
        prompt: str,
        schema: Dict[str, Any],
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ) -> Dict[str, Any]:
        """Generate and parse a JSON object, enforcing required top-level fields."""
        content = await self.generate_text(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            reasoning_config=reasoning_config,
        )
        value = parse_json(content)
        if not isinstance(value, dict):
            raise ValueError("结构化输出必须是 JSON 对象")
        missing = [name for name in schema.get("required", []) if name not in value]
        if missing:
            raise ValueError(f"结构化输出缺少必填字段: {', '.join(missing)}")
        return value

    def get_capabilities(self) -> AICapabilities:
        """Return conservative defaults; providers override supported extensions."""
        return AICapabilities()

    async def close(self) -> None:
        """Release provider-owned resources when the implementation requires it."""
        return None

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        user_id: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
        mcp_max_rounds: int = 3,
        allowed_tool_names: Optional[set[str]] = None,
        db_session: Any = None,
    ) -> AsyncGenerator[str | Dict[str, Any], None]:
        """流式生成"""
        if False:
            yield {}
