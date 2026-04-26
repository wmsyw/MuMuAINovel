"""AI Provider 基类"""
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.services.ai_capabilities import ReasoningConfig


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
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ) -> Dict[str, Any]:
        """生成文本"""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        user_id: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成"""
        pass
