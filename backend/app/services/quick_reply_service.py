"""Quick reply safe-snippet service layer."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.creative_session import CreativeSession, CreativeSessionMessage
from app.models.quick_reply import SAFE_SNIPPET_ACTION_TYPE, QuickReply
from app.services.creative_session_service import CreativeSessionService


MAX_SAFE_SNIPPET_CHARS = 4000


class QuickReplyValidationError(ValueError):
    """Raised when a quick reply attempts to leave the safe-snippet boundary."""


_UNSAFE_SNIPPET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?is)<\s*/?\s*script\b"), "不允许HTML脚本片段"),
    (re.compile(r"(?i)\bjavascript\s*:"), "不允许JavaScript URL或脚本协议"),
    (re.compile(r"(?s)\{\{.*?\}\}"), "不兼容STscript/宏模板语法"),
    (re.compile(r"(?s)(?:\$\{|<%|\{%|%\})"), "不允许可执行模板语法"),
    (
        re.compile(
            r"(?im)^\s*/(?:send|setvar|getvar|run|exec|system|shell|fetch|api|trigger|inject|prompt|let|if|while|delay|abort|echo)\b"
        ),
        "不允许Slash/STscript命令",
    ),
    (re.compile(r"(?i)\b(?:curl|wget)\s+https?://"), "不允许网络命令"),
    (re.compile(r"(?i)\b(?:bash|zsh|sh|powershell|cmd|python|node|ruby|perl)\s+(?:-c|/c|-e)\b"), "不允许Shell/解释器命令"),
    (re.compile(r"(?i)\b(?:fetch|XMLHttpRequest|axios)\s*\("), "不允许网络请求代码"),
)


def validate_safe_snippet_text(snippet: str) -> str:
    """Validate and normalize a static snippet without interpreting macro syntax."""

    text = str(snippet or "").strip()
    if not text:
        raise QuickReplyValidationError("快捷片段内容不能为空")
    if len(text) > MAX_SAFE_SNIPPET_CHARS:
        raise QuickReplyValidationError(f"快捷片段不能超过 {MAX_SAFE_SNIPPET_CHARS} 字符")
    for pattern, message in _UNSAFE_SNIPPET_PATTERNS:
        if pattern.search(text):
            raise QuickReplyValidationError(message)
    return text


def validate_action_type(action_type: str | None) -> str:
    """Normalize the only supported quick action type."""

    normalized = str(action_type or SAFE_SNIPPET_ACTION_TYPE).strip()
    if normalized != SAFE_SNIPPET_ACTION_TYPE:
        raise QuickReplyValidationError("仅支持 safe_snippet 快捷操作；不允许脚本、命令或远程动作")
    return normalized


class QuickReplyService:
    """Project-scoped quick reply CRUD and explicit creative-session application."""

    @staticmethod
    def reply_dict(reply: QuickReply) -> dict[str, Any]:
        return {
            "id": reply.id,
            "project_id": reply.project_id,
            "user_id": reply.user_id,
            "label": reply.label,
            "action_type": reply.action_type,
            "snippet": reply.snippet,
            "sort_order": reply.sort_order,
            "enabled": bool(reply.enabled),
            "created_at": reply.created_at,
            "updated_at": reply.updated_at,
        }

    @staticmethod
    def application_trace(reply: QuickReply) -> dict[str, Any]:
        return {
            "source_type": "quick_reply",
            "trace_label": f"quick_reply:{reply.label}",
            "quick_reply_id": reply.id,
            "label": reply.label,
            "action_type": SAFE_SNIPPET_ACTION_TYPE,
            "applied_content": reply.snippet,
            "prompt_mutation": False,
            "boundary_decision": "explicit_safe_snippet_session_insert",
        }

    @classmethod
    async def create_reply(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        label: str,
        snippet: str,
        sort_order: int = 0,
        enabled: bool = True,
        action_type: str = SAFE_SNIPPET_ACTION_TYPE,
    ) -> QuickReply:
        safe_action_type = validate_action_type(action_type)
        safe_snippet = validate_safe_snippet_text(snippet)
        reply = QuickReply(
            project_id=project_id,
            user_id=user_id,
            label=label.strip(),
            action_type=safe_action_type,
            snippet=safe_snippet,
            sort_order=sort_order,
            enabled=enabled,
        )
        db.add(reply)
        await db.commit()
        await db.refresh(reply)
        return reply

    @classmethod
    async def list_replies(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[QuickReply]]:
        filters = [QuickReply.project_id == project_id, QuickReply.user_id == user_id]
        if enabled is not None:
            filters.append(QuickReply.enabled == enabled)
        count_result = await db.execute(select(func.count(QuickReply.id)).where(*filters))
        result = await db.execute(
            select(QuickReply)
            .where(*filters)
            .order_by(QuickReply.sort_order.asc(), QuickReply.label.asc(), QuickReply.created_at.asc(), QuickReply.id.asc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return int(count_result.scalar_one() or 0), list(result.scalars().all())

    @classmethod
    async def get_reply(cls, *, db: AsyncSession, reply_id: str, user_id: str) -> QuickReply | None:
        result = await db.execute(select(QuickReply).where(QuickReply.id == reply_id, QuickReply.user_id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def update_reply(
        cls,
        *,
        db: AsyncSession,
        reply: QuickReply,
        updates: dict[str, Any],
    ) -> QuickReply:
        if "action_type" in updates:
            reply.action_type = validate_action_type(updates["action_type"])
        if "label" in updates and updates["label"] is not None:
            reply.label = str(updates["label"]).strip()
        if "snippet" in updates and updates["snippet"] is not None:
            reply.snippet = validate_safe_snippet_text(str(updates["snippet"]))
        if "sort_order" in updates and updates["sort_order"] is not None:
            reply.sort_order = int(updates["sort_order"])
        if "enabled" in updates and updates["enabled"] is not None:
            reply.enabled = bool(updates["enabled"])
        await db.commit()
        await db.refresh(reply)
        return reply

    @classmethod
    async def delete_reply(cls, *, db: AsyncSession, reply: QuickReply) -> None:
        await db.delete(reply)
        await db.commit()

    @classmethod
    async def apply_to_creative_session(
        cls,
        *,
        db: AsyncSession,
        reply: QuickReply,
        session: CreativeSession,
        user_id: str,
    ) -> tuple[CreativeSessionMessage, dict[str, Any]]:
        safe_action_type = validate_action_type(reply.action_type)
        if not reply.enabled:
            raise QuickReplyValidationError("快捷片段已停用")
        safe_snippet = validate_safe_snippet_text(reply.snippet)
        trace = cls.application_trace(reply)
        message = await CreativeSessionService.append_message(
            db=db,
            session=session,
            user_id=user_id,
            role="note",
            content=safe_snippet,
            metadata={
                "source": "quick_reply",
                "source_type": "quick_reply",
                "action_type": safe_action_type,
                "quick_reply_id": reply.id,
                "quick_reply_label": reply.label,
                "trace_label": trace["trace_label"],
                "prompt_mutation": False,
                "applied_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
        )
        return message, trace
