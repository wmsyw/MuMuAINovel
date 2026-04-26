"""OpenAI Provider"""
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.logger import get_logger
from app.services.ai_capabilities import ReasoningConfig
from app.services.ai_clients.openai_client import OpenAIClient
from .base_provider import BaseAIProvider

logger = get_logger(__name__)


class OpenAIProvider(BaseAIProvider):
    """OpenAI 提供商"""

    def __init__(self, client: OpenAIClient):
        self.client = client

    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _uses_responses_api(self, reasoning_config: Optional[ReasoningConfig]) -> bool:
        """Responses routing is driven by Task 4 provider payload, not model-name branches."""
        if not reasoning_config or not reasoning_config.provider_payload:
            return False
        capability = reasoning_config.capability
        provider_native = capability.provider_native if capability else ""
        reasoning = reasoning_config.provider_payload.get("reasoning")
        if not provider_native.startswith("responses.") or not isinstance(reasoning, dict):
            return False

        # `off`/`none` remains compatible with the legacy Chat Completions path.
        return reasoning.get("effort") not in {None, "none", "off"}

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
        messages = self._build_messages(prompt, system_prompt)

        if self._uses_responses_api(reasoning_config):
            return await self.client.create_response(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                reasoning_payload=reasoning_config.provider_payload if reasoning_config else None,
            )

        return await self.client.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
        )

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
        messages = self._build_messages(prompt, system_prompt)
        use_responses = self._uses_responses_api(reasoning_config)

        # 如果有工具，使用真正的流式工具调用
        if tools:
            logger.debug(f"🔧 OpenAIProvider: 有 {len(tools)} 个工具，使用流式处理")
            actual_tool_choice = tool_choice if tool_choice else "auto"
            
            tool_calls_buffer = []
            
            stream = self.client.create_response_stream if use_responses else self.client.chat_completion_stream
            async for chunk in stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=actual_tool_choice,
                **({"reasoning_payload": reasoning_config.provider_payload} if use_responses and reasoning_config else {}),
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
                            tool_calls=tool_calls_buffer
                        )
                        # 将工具结果注入到上下文中
                        tool_context = mcp_client.build_tool_context(tool_results, format="markdown")
                        
                        # 构建最终提示词，要求AI基于工具结果回答
                        final_prompt = f"{prompt}\n\n{tool_context}\n\n请基于以上工具查询结果，给出完整详细的回答。"
                        final_messages = messages.copy()
                        final_messages.append({"role": "user", "content": final_prompt})
                        
                        # 递归调用生成最终结果
                        async for final_chunk in self._generate_with_tools(
                            final_messages, model, temperature, max_tokens, tools, user_id
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
        stream = self.client.create_response_stream if use_responses else self.client.chat_completion_stream
        async for chunk in stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **({"reasoning_payload": reasoning_config.provider_payload} if use_responses and reasoning_config else {}),
        ):
            if isinstance(chunk, dict):
                if chunk.get("usage"):
                    yield {"usage": chunk.get("usage")}
                if chunk.get("finish_reason"):
                    yield {"finish_reason": chunk.get("finish_reason"), "done": chunk.get("done", False)}
                if chunk.get("provider_metadata") or chunk.get("reasoning_continuation"):
                    yield {
                        "provider_metadata": chunk.get("provider_metadata"),
                        "reasoning_continuation": chunk.get("reasoning_continuation"),
                    }
                if chunk.get("content"):
                    yield chunk["content"]
            else:
                yield chunk

    async def _generate_with_tools(
        self,
        messages: list,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """辅助方法：带工具的流式生成（无tool_choice，AI自由决定）"""
        async for chunk in self.client.chat_completion_stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice="auto",
        ):
            if chunk.get("tool_calls"):
                from app.mcp import mcp_client
                actual_user_id = user_id or ""
                tool_results = await mcp_client.batch_call_tools(
                    user_id=actual_user_id,
                    tool_calls=chunk["tool_calls"]
                )
                tool_context = mcp_client.build_tool_context(tool_results, format="markdown")
                
                # 再次调用获取最终回答
                messages.append({"role": "user", "content": f"{tool_context}\n\n请基于以上工具查询结果，给出完整详细的回答。"})
                
                async for final_chunk in self._generate_with_tools(
                    messages, model, temperature, max_tokens, tools, user_id
                ):
                    yield final_chunk
                break
            
            if chunk.get("done"):
                if chunk.get("finish_reason"):
                    yield {"finish_reason": chunk.get("finish_reason"), "done": True}
                break

            if chunk.get("usage"):
                yield {"usage": chunk.get("usage")}
            
            if chunk.get("content"):
                yield chunk["content"]
