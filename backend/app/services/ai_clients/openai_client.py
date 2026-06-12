"""OpenAI 客户端"""
from copy import deepcopy
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.logger import get_logger, summarize_log_value
from app.services.ai_token_limits import resolve_openai_compatible_max_tokens
from .base_client import BaseAIClient

logger = get_logger(__name__)


def _message_content_length(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    return len(json.dumps(content, ensure_ascii=False, default=str))


def _log_request_summary(payload: Dict[str, Any]) -> None:
    messages = payload.get("messages") or []
    message_chars = sum(_message_content_length(message.get("content")) for message in messages if isinstance(message, dict))
    logger.debug(
        "📤 OpenAI 请求摘要: model=%s, messages=%s, message_chars=%s, tools=%s, stream=%s, max_tokens=%s",
        payload.get("model"),
        len(messages),
        message_chars,
        len(payload.get("tools") or []),
        bool(payload.get("stream")),
        payload.get("max_tokens"),
    )


def _log_response_summary(data: Dict[str, Any]) -> None:
    choices = data.get("choices") or []
    first_choice = choices[0] if choices else {}
    message = first_choice.get("message") or {}
    content = message.get("content") or ""
    tool_calls = message.get("tool_calls") or []
    usage = data.get("usage") or {}
    logger.debug(
        "📥 OpenAI 响应摘要: choices=%s, finish_reason=%s, content_length=%s, tool_calls=%s, usage=%s",
        len(choices),
        first_choice.get("finish_reason"),
        len(content) if isinstance(content, str) else _message_content_length(content),
        len(tool_calls),
        summarize_log_value(usage),
    )


class OpenAIClient(BaseAIClient):
    """OpenAI API 客户端"""

    _MAX_ERROR_BODY_LOG_CHARS: int = 2000

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _clean_chat_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None

        cleaned = []
        for tool in tools:
            tool_copy = deepcopy(tool)
            if "function" in tool_copy and "parameters" in tool_copy["function"]:
                tool_copy["function"]["parameters"] = {
                    key: value
                    for key, value in tool_copy["function"]["parameters"].items()
                    if key != "$schema"
                }
            cleaned.append(tool_copy)
        return cleaned

    def _clean_response_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """将现有 Chat Completions function tool 形状转换为 Responses tool 形状。"""
        if not tools:
            return None

        response_tools = []
        for tool in self._clean_chat_tools(tools) or []:
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                function = tool["function"]
                converted = {
                    "type": "function",
                    "name": function.get("name"),
                    "description": function.get("description") or function.get("name"),
                    "parameters": function.get("parameters") or {"type": "object", "properties": {}},
                }
                response_tools.append(converted)
            else:
                response_tools.append(tool)
        return response_tools

    def _normalize_chat_tool_choice(
        self,
        tool_choice: Optional[str],
        provider_compatibility: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        if not tool_choice:
            return None
        if tool_choice == "required" and provider_compatibility:
            replacement = provider_compatibility.get("chat_tool_choice_required")
            if isinstance(replacement, str) and replacement:
                logger.info(f"OpenAI兼容请求按模型能力配置将 tool_choice=required 调整为 {replacement}")
                return replacement
        return tool_choice

    async def _normalize_max_tokens(self, model: str, max_tokens: int) -> int:
        resolution = await resolve_openai_compatible_max_tokens(model=model, max_tokens=max_tokens)
        if resolution.normalized != max_tokens:
            logger.warning(
                "OpenAI兼容请求 max_tokens=%s 超出模型输出上限，已调整为 %s（上限=%s｜来源=%s｜匹配=%s/%s）",
                max_tokens,
                resolution.normalized,
                resolution.limit,
                resolution.source,
                resolution.matched_provider,
                resolution.matched_model,
            )
        return resolution.normalized

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
        reasoning_payload: Optional[Dict[str, Any]] = None,
        provider_compatibility: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        if reasoning_payload:
            payload.update(deepcopy(reasoning_payload))
        cleaned_tools = self._clean_chat_tools(tools)
        if cleaned_tools:
            payload["tools"] = cleaned_tools
            actual_tool_choice = self._normalize_chat_tool_choice(tool_choice, provider_compatibility)
            if actual_tool_choice:
                payload["tool_choice"] = actual_tool_choice
        return payload

    def _content_length(self, content: Any) -> int:
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            return sum(self._content_length(item.get("text") or item.get("content")) for item in content if isinstance(item, dict))
        if content is None:
            return 0
        return len(str(content))

    def _payload_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        messages = payload.get("messages")
        if not isinstance(messages, list):
            messages = []
        tools = payload.get("tools")
        if not isinstance(tools, list):
            tools = []
        payload_keys = sorted(payload.keys())
        standard_keys = {"model", "messages", "temperature", "max_tokens", "stream", "tools", "tool_choice"}

        return {
            "model": payload.get("model"),
            "endpoint_payload_keys": payload_keys,
            "nonstandard_payload_keys": [key for key in payload_keys if key not in standard_keys],
            "stream": payload.get("stream", False),
            "temperature": payload.get("temperature"),
            "max_tokens": payload.get("max_tokens"),
            "message_count": len(messages),
            "message_roles": [message.get("role") for message in messages if isinstance(message, dict)],
            "message_content_lengths": [
                self._content_length(message.get("content"))
                for message in messages
                if isinstance(message, dict)
            ],
            "tool_count": len(tools),
            "tool_choice": payload.get("tool_choice"),
        }

    async def _upstream_error_body(self, response: httpx.Response) -> str:
        try:
            await response.aread()
        except Exception:
            return "<无法读取上游错误响应体>"
        body = response.text.strip()
        if len(body) > self._MAX_ERROR_BODY_LOG_CHARS:
            return f"{body[:self._MAX_ERROR_BODY_LOG_CHARS]}...(truncated)"
        return body or "<空响应体>"

    async def _log_upstream_http_error(
        self,
        exc: httpx.HTTPStatusError,
        *,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> None:
        body = await self._upstream_error_body(exc.response)
        logger.error(
            "OpenAI兼容上游HTTP错误｜端点=%s｜状态码=%s｜URL=%s｜响应体=%s｜payload摘要=%s",
            endpoint,
            exc.response.status_code,
            exc.response.url,
            body,
            json.dumps(self._payload_summary(payload), ensure_ascii=False, separators=(",", ":")),
        )

    def _build_response_input(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        input_items = []
        for message in messages:
            role = message.get("role") or "user"
            content = message.get("content", "")
            if isinstance(content, list):
                input_content = content
            else:
                input_content = [{"type": "input_text", "text": str(content)}]
            input_items.append({"role": role, "content": input_content})
        return input_items

    def _build_response_payload(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
        reasoning_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "input": self._build_response_input(messages),
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        if reasoning_payload:
            payload.update(deepcopy(reasoning_payload))

        response_tools = self._clean_response_tools(tools)
        if response_tools:
            payload["tools"] = response_tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        return payload

    def _normalize_usage(self, usage: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        usage = usage or {}
        prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        total_tokens = usage.get("total_tokens")
        if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _extract_response_text_and_tools(self, output_items: List[Dict[str, Any]]) -> tuple[str, Optional[List[Dict[str, Any]]]]:
        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        for item in output_items or []:
            item_type = item.get("type")
            if item_type == "message":
                for content_item in item.get("content") or []:
                    text = content_item.get("text")
                    if text and content_item.get("type") in {"output_text", "text"}:
                        content_parts.append(text)
            elif item_type in {"function_call", "tool_call"}:
                name = item.get("name") or item.get("function", {}).get("name")
                arguments = item.get("arguments") or item.get("function", {}).get("arguments") or ""
                tool_calls.append({
                    "id": item.get("call_id") or item.get("id") or f"call_{name or len(tool_calls)}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                })
            elif item_type in {"output_text", "text"} and item.get("text"):
                content_parts.append(item["text"])

        return "".join(content_parts), tool_calls or None

    def _normalize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        content, tool_calls = self._extract_response_text_and_tools(data.get("output") or [])
        finish_reason = data.get("finish_reason")
        status = data.get("status")
        if finish_reason is None:
            if tool_calls:
                finish_reason = "tool_calls"
            elif status == "completed":
                finish_reason = "stop"
            else:
                finish_reason = status

        metadata = {
            "response_id": data.get("id"),
            "status": status,
            "model": data.get("model"),
            "object": data.get("object"),
        }
        reasoning_continuation = {
            key: value
            for key, value in {
                "previous_response_id": data.get("previous_response_id"),
                "reasoning": data.get("reasoning"),
                "incomplete_details": data.get("incomplete_details"),
            }.items()
            if value is not None
        }
        return {
            "content": content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "usage": self._normalize_usage(data.get("usage")),
            "provider_metadata": {key: value for key, value in metadata.items() if value is not None},
            "reasoning_continuation": reasoning_continuation or None,
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        reasoning_payload: Optional[Dict[str, Any]] = None,
        provider_compatibility: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_max_tokens = await self._normalize_max_tokens(model, max_tokens)
        payload = self._build_payload(
            messages,
            model,
            temperature,
            normalized_max_tokens,
            tools,
            tool_choice,
            reasoning_payload=reasoning_payload,
            provider_compatibility=provider_compatibility,
        )
        
        _log_request_summary(payload)
        
        try:
            data = await self._request_with_retry("POST", "/chat/completions", payload)
        except httpx.HTTPStatusError as exc:
            await self._log_upstream_http_error(exc, endpoint="/chat/completions", payload=payload)
            raise
        
        _log_response_summary(data)

        choices = data.get("choices", [])
        if not choices or len(choices) == 0:
            raise ValueError("API 返回空 choices 或 choices 为空列表")

        choice = choices[0]
        message = choice.get("message", {})
        usage = data.get("usage") or {}
        return {
            "content": message.get("content", ""),
            "tool_calls": message.get("tool_calls"),
            "finish_reason": choice.get("finish_reason"),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
        }

    async def create_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        reasoning_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_max_tokens = await self._normalize_max_tokens(model, max_tokens)
        payload = self._build_response_payload(
            messages,
            model,
            temperature,
            normalized_max_tokens,
            tools,
            tool_choice,
            reasoning_payload=reasoning_payload,
        )

        logger.debug(f"📤 OpenAI Responses 请求 payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
        try:
            data = await self._request_with_retry("POST", "/responses", payload)
        except httpx.HTTPStatusError as exc:
            await self._log_upstream_http_error(exc, endpoint="/responses", payload=payload)
            raise
        logger.debug(f"📥 OpenAI Responses 原始响应: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return self._normalize_response(data)

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        reasoning_payload: Optional[Dict[str, Any]] = None,
        provider_compatibility: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式生成，支持工具调用
        
        Yields:
            Dict with keys:
            - content: str - 文本内容块
            - tool_calls: list - 工具调用列表（如果有）
            - done: bool - 是否结束
        """
        normalized_max_tokens = await self._normalize_max_tokens(model, max_tokens)
        payload = self._build_payload(
            messages,
            model,
            temperature,
            normalized_max_tokens,
            tools,
            tool_choice,
            stream=True,
            reasoning_payload=reasoning_payload,
            provider_compatibility=provider_compatibility,
        )
        
        tool_calls_buffer = {}  # 收集工具调用块
        
        try:
            async with await self._request_with_retry("POST", "/chat/completions", payload, stream=True) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    await self._log_upstream_http_error(exc, endpoint="/chat/completions", payload=payload)
                    raise
                try:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                # 流结束，检查是否有工具调用需要处理
                                if tool_calls_buffer:
                                    yield {"tool_calls": list(tool_calls_buffer.values()), "done": True}
                                yield {"done": True}
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices and len(choices) > 0:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    
                                    # 检查工具调用
                                    tc_list = delta.get("tool_calls")
                                    if tc_list:
                                        for tc in tc_list:
                                            index = tc.get("index", 0)
                                            if index not in tool_calls_buffer:
                                                tool_calls_buffer[index] = tc
                                            else:
                                                existing = tool_calls_buffer[index]
                                                # 合并 function.arguments
                                                if "function" in tc and "function" in existing:
                                                    if tc["function"].get("arguments"):
                                                        existing["function"]["arguments"] = (
                                                            existing["function"].get("arguments", "") +
                                                            tc["function"]["arguments"]
                                                        )

                                    usage = data.get("usage")
                                    if usage:
                                        yield {
                                            "usage": {
                                                "prompt_tokens": usage.get("prompt_tokens"),
                                                "completion_tokens": usage.get("completion_tokens"),
                                                "total_tokens": usage.get("total_tokens"),
                                            }
                                        }
                                    
                                    if content:
                                        yield {"content": content}
                                        
                            except json.JSONDecodeError:
                                continue
                except GeneratorExit:
                    # 生成器被关闭，这是正常的清理过程
                    logger.debug("流式响应生成器被关闭(GeneratorExit)")
                    raise
                except Exception as iter_error:
                    logger.error(f"流式响应迭代出错: {str(iter_error)}")
                    raise
        except GeneratorExit:
            # 重新抛出GeneratorExit，让调用方处理
            raise
        except Exception as e:
            logger.error(f"流式请求出错: {str(e)}")
            raise

    async def create_response_stream(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        reasoning_payload: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        normalized_max_tokens = await self._normalize_max_tokens(model, max_tokens)
        payload = self._build_response_payload(
            messages,
            model,
            temperature,
            normalized_max_tokens,
            tools,
            tool_choice,
            stream=True,
            reasoning_payload=reasoning_payload,
        )

        tool_calls_buffer: Dict[str, Dict[str, Any]] = {}

        try:
            async with await self._request_with_retry("POST", "/responses", payload, stream=True) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    await self._log_upstream_http_error(exc, endpoint="/responses", payload=payload)
                    raise
                try:
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            if tool_calls_buffer:
                                yield {"tool_calls": list(tool_calls_buffer.values())}
                            yield {"done": True, "finish_reason": "stop"}
                            break
                        try:
                            event = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event.get("type")
                        if event_type in {"response.output_text.delta", "response.text.delta"}:
                            delta = event.get("delta") or ""
                            if delta:
                                yield {"content": delta}
                        elif event_type == "response.output_item.added":
                            item = event.get("item") or {}
                            if item.get("type") in {"function_call", "tool_call"}:
                                item_id = item.get("id") or item.get("call_id") or str(event.get("output_index", len(tool_calls_buffer)))
                                tool_calls_buffer[item_id] = {
                                    "id": item.get("call_id") or item.get("id") or item_id,
                                    "type": "function",
                                    "function": {
                                        "name": item.get("name") or item.get("function", {}).get("name"),
                                        "arguments": item.get("arguments") or item.get("function", {}).get("arguments") or "",
                                    },
                                }
                        elif event_type == "response.function_call_arguments.delta":
                            item_id = event.get("item_id") or str(event.get("output_index", 0))
                            existing = tool_calls_buffer.setdefault(
                                item_id,
                                {"id": item_id, "type": "function", "function": {"name": None, "arguments": ""}},
                            )
                            existing["function"]["arguments"] += event.get("delta") or ""
                        elif event_type == "response.output_item.done":
                            item = event.get("item") or {}
                            if item.get("type") in {"function_call", "tool_call"}:
                                item_id = item.get("id") or item.get("call_id") or str(event.get("output_index", len(tool_calls_buffer)))
                                tool_calls_buffer[item_id] = {
                                    "id": item.get("call_id") or item.get("id") or item_id,
                                    "type": "function",
                                    "function": {
                                        "name": item.get("name") or item.get("function", {}).get("name"),
                                        "arguments": item.get("arguments") or item.get("function", {}).get("arguments") or tool_calls_buffer.get(item_id, {}).get("function", {}).get("arguments", ""),
                                    },
                                }
                        elif event_type in {"response.completed", "response.done", "response.incomplete", "response.failed"}:
                            normalized = self._normalize_response(event.get("response") or {})
                            if tool_calls_buffer:
                                yield {"tool_calls": list(tool_calls_buffer.values())}
                                tool_calls_buffer.clear()
                            if normalized.get("usage"):
                                yield {"usage": normalized["usage"]}
                            if normalized.get("provider_metadata") or normalized.get("reasoning_continuation"):
                                yield {
                                    "provider_metadata": normalized.get("provider_metadata"),
                                    "reasoning_continuation": normalized.get("reasoning_continuation"),
                                }
                            yield {"done": True, "finish_reason": normalized.get("finish_reason")}
                            break
                except GeneratorExit:
                    logger.debug("OpenAI Responses 流式响应生成器被关闭(GeneratorExit)")
                    raise
                except Exception as iter_error:
                    logger.error(f"OpenAI Responses 流式响应迭代出错: {str(iter_error)}")
                    raise
        except GeneratorExit:
            raise
        except Exception as e:
            logger.error(f"OpenAI Responses 流式请求出错: {str(e)}")
            raise
