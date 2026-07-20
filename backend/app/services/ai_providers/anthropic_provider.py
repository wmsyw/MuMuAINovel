"""Anthropic Provider"""
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.logger import get_logger
from app.services.ai_capabilities import ReasoningConfig
from app.services.ai_clients.anthropic_client import AnthropicClient
from .base_provider import AICapabilities, BaseAIProvider

logger = get_logger(__name__)


class AnthropicProvider(BaseAIProvider):
    """Anthropic 提供商"""

    def __init__(self, client: AnthropicClient):
        self.client = client

    def get_capabilities(self) -> AICapabilities:
        return AICapabilities(tools=True, reasoning=True)

    async def close(self) -> None:
        await self.client.close()

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
        messages = [{"role": "user", "content": prompt}]
        return await self.client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            tools=tools,
            tool_choice=tool_choice,
            reasoning_payload=reasoning_config.provider_payload if reasoning_config else None,
        )

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
        if mcp_max_rounds <= 0:
            tools = None
        # 如果有工具，使用真正的流式工具调用
        if tools:
            logger.debug(f"🔧 AnthropicProvider: 有 {len(tools)} 个工具，使用流式处理")
            messages = [{"role": "user", "content": prompt}]
            actual_tool_choice = tool_choice if tool_choice else "auto"
            
            tool_calls_buffer = []
            
            async for chunk in self.client.chat_completion_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                tools=tools,
                tool_choice=actual_tool_choice,
                reasoning_payload=reasoning_config.provider_payload if reasoning_config else None,
            ):
                # 检查是否有工具调用
                if chunk.get("tool_calls"):
                    tool_calls_buffer.extend(chunk["tool_calls"])
                    logger.debug(f"🔧 收到工具调用: {len(chunk['tool_calls'])} 个")
                
                # 检查是否结束
                if chunk.get("done"):
                    if tool_calls_buffer:
                        logger.info(f"🔧 流式结束，处理 {len(tool_calls_buffer)} 个工具调用")
                        from app.mcp import mcp_client
                        actual_user_id = user_id or ""
                        tool_results = await mcp_client.batch_call_tools(
                            user_id=actual_user_id,
                            tool_calls=tool_calls_buffer,
                            allowed_function_names=allowed_tool_names,
                            db_session=db_session,
                        )
                        # 将工具结果注入到上下文中
                        tool_context = mcp_client.build_tool_context(tool_results, format="markdown")
                        
                        # 构建最终提示词，要求AI基于工具结果回答
                        final_prompt = f"{prompt}\n\n{tool_context}\n\n请基于以上工具查询结果，给出完整详细的回答。"
                        final_messages = [{"role": "user", "content": final_prompt}]
                        
                        # 递归调用生成最终结果
                        async for final_chunk in self._generate_with_tools(
                            final_messages,
                            model,
                            temperature,
                            max_tokens,
                            system_prompt,
                            tools,
                            user_id,
                            reasoning_config,
                            rounds_remaining=mcp_max_rounds - 1,
                            allowed_tool_names=allowed_tool_names,
                            db_session=db_session,
                        ):
                            yield final_chunk
                    if chunk.get("finish_reason"):
                        yield {"finish_reason": chunk.get("finish_reason"), "done": True}
                    break

                if chunk.get("usage"):
                    yield {"usage": chunk.get("usage")}
                
                # 输出文本内容
                if chunk.get("content"):
                    yield chunk["content"]
            return
        
        # 无工具时普通流式生成
        messages = [{"role": "user", "content": prompt}]
        async for chunk in self.client.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            reasoning_payload=reasoning_config.provider_payload if reasoning_config else None,
        ):
            if isinstance(chunk, dict):
                if chunk.get("usage"):
                    yield {"usage": chunk.get("usage")}
                if chunk.get("finish_reason"):
                    yield {"finish_reason": chunk.get("finish_reason")}
                if chunk.get("content"):
                    yield chunk["content"]
            else:
                yield chunk

    async def _generate_with_tools(
        self,
        messages: list[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        system_prompt: Optional[str] = None,
        tools: Optional[list[Dict[str, Any]]] = None,
        user_id: Optional[str] = None,
        reasoning_config: Optional[ReasoningConfig] = None,
        rounds_remaining: int = 1,
        allowed_tool_names: Optional[set[str]] = None,
        db_session: Any = None,
    ) -> AsyncGenerator[str | Dict[str, Any], None]:
        """辅助方法：带工具的流式生成"""
        tool_calls_buffer = []
        active_tools = tools if rounds_remaining > 0 else None
        
        async for chunk in self.client.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            tools=active_tools,
            tool_choice="auto" if active_tools else None,
            reasoning_payload=reasoning_config.provider_payload if reasoning_config else None,
        ):
            if chunk.get("tool_calls") and rounds_remaining > 0:
                tool_calls_buffer.extend(chunk["tool_calls"])
                logger.debug(f"🔧 _generate_with_tools 收到工具调用: {len(chunk['tool_calls'])} 个")
            
            if chunk.get("done"):
                if tool_calls_buffer:
                    from app.mcp import mcp_client
                    actual_user_id = user_id or ""
                    tool_results = await mcp_client.batch_call_tools(
                        user_id=actual_user_id,
                        tool_calls=tool_calls_buffer,
                        allowed_function_names=allowed_tool_names,
                        db_session=db_session,
                    )
                    tool_context = mcp_client.build_tool_context(tool_results, format="markdown")
                    
                    messages.append({"role": "user", "content": f"{tool_context}\n\n请基于以上工具查询结果，给出完整详细的回答。"})
                    
                    async for final_chunk in self._generate_with_tools(
                        messages,
                        model,
                        temperature,
                        max_tokens,
                        system_prompt,
                        tools,
                        user_id,
                        reasoning_config,
                        rounds_remaining=rounds_remaining - 1,
                        allowed_tool_names=allowed_tool_names,
                        db_session=db_session,
                    ):
                        yield final_chunk
                if chunk.get("finish_reason"):
                    yield {"finish_reason": chunk.get("finish_reason"), "done": True}
                break

            if chunk.get("usage"):
                yield {"usage": chunk.get("usage")}
            
            if chunk.get("content"):
                yield chunk["content"]
