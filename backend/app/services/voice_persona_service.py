"""Narrator voice persona service layer."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_persona import VOICE_PERSONA_PROJECT_SCOPE, VOICE_PERSONA_SESSION_SCOPE, VoicePersona


MAX_TONE_CHARS = 2000
MAX_STYLE_CHARS = 2000
MAX_POINT_OF_VIEW_CHARS = 1000
MAX_CONSTRAINTS_CHARS = 4000


class VoicePersonaValidationError(ValueError):
    """Raised when a voice profile leaves the authoring-profile boundary."""


def _clean_text(value: Any, *, max_chars: int, field_name: str) -> str:
    text = str(value or "").strip()
    if len(text) > max_chars:
        raise VoicePersonaValidationError(f"{field_name}不能超过 {max_chars} 字符")
    return text


def _clean_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        raise VoicePersonaValidationError("声音画像名称不能为空")
    if len(name) > 120:
        raise VoicePersonaValidationError("声音画像名称不能超过 120 字符")
    return name


def _scope_from_session(session_id: str | None) -> str:
    return VOICE_PERSONA_SESSION_SCOPE if session_id else VOICE_PERSONA_PROJECT_SCOPE


def _normalize_authoring_fields(
    *,
    tone: Any,
    style: Any,
    point_of_view: Any,
    constraints: Any,
) -> dict[str, str]:
    fields = {
        "tone": _clean_text(tone, max_chars=MAX_TONE_CHARS, field_name="语气"),
        "style": _clean_text(style, max_chars=MAX_STYLE_CHARS, field_name="文风"),
        "point_of_view": _clean_text(point_of_view, max_chars=MAX_POINT_OF_VIEW_CHARS, field_name="叙事视角"),
        "constraints": _clean_text(constraints, max_chars=MAX_CONSTRAINTS_CHARS, field_name="写作约束"),
    }
    if not any(fields.values()):
        raise VoicePersonaValidationError("至少填写语气、文风、视角或约束中的一项")
    return fields


class VoicePersonaService:
    """Project/session-scoped narrator voice profile CRUD and trace inputs."""

    @staticmethod
    def persona_dict(persona: VoicePersona) -> dict[str, Any]:
        return {
            "id": persona.id,
            "project_id": persona.project_id,
            "user_id": persona.user_id,
            "session_id": persona.session_id,
            "scope": persona.scope,
            "name": persona.name,
            "tone": persona.tone,
            "style": persona.style,
            "point_of_view": persona.point_of_view,
            "constraints": persona.constraints,
            "sort_order": persona.sort_order,
            "enabled": bool(persona.enabled),
            "created_at": persona.created_at,
            "updated_at": persona.updated_at,
        }

    @classmethod
    async def create_persona(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        name: str,
        tone: str = "",
        style: str = "",
        point_of_view: str = "",
        constraints: str = "",
        session_id: str | None = None,
        sort_order: int = 0,
        enabled: bool = True,
    ) -> VoicePersona:
        fields = _normalize_authoring_fields(tone=tone, style=style, point_of_view=point_of_view, constraints=constraints)
        persona = VoicePersona(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            scope=_scope_from_session(session_id),
            name=_clean_name(name),
            tone=fields["tone"],
            style=fields["style"],
            point_of_view=fields["point_of_view"],
            constraints=fields["constraints"],
            sort_order=int(sort_order),
            enabled=bool(enabled),
        )
        db.add(persona)
        await db.commit()
        await db.refresh(persona)
        return persona

    @classmethod
    async def list_personas(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        session_id: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[VoicePersona]]:
        filters: list[Any] = [VoicePersona.project_id == project_id, VoicePersona.user_id == user_id]
        if session_id:
            filters.append(or_(VoicePersona.session_id.is_(None), VoicePersona.session_id == session_id))
        else:
            filters.append(VoicePersona.session_id.is_(None))
        if enabled is not None:
            filters.append(VoicePersona.enabled == enabled)

        count_result = await db.execute(select(func.count(VoicePersona.id)).where(*filters))
        result = await db.execute(
            select(VoicePersona)
            .where(*filters)
            .order_by(VoicePersona.scope.asc(), VoicePersona.sort_order.asc(), VoicePersona.name.asc(), VoicePersona.created_at.asc(), VoicePersona.id.asc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return int(count_result.scalar_one() or 0), list(result.scalars().all())

    @classmethod
    async def get_persona(
        cls,
        *,
        db: AsyncSession,
        persona_id: str,
        user_id: str,
        project_id: str | None = None,
    ) -> VoicePersona | None:
        filters: list[Any] = [VoicePersona.id == persona_id, VoicePersona.user_id == user_id]
        if project_id is not None:
            filters.append(VoicePersona.project_id == project_id)
        result = await db.execute(select(VoicePersona).where(*filters))
        return result.scalar_one_or_none()

    @classmethod
    async def update_persona(
        cls,
        *,
        db: AsyncSession,
        persona: VoicePersona,
        updates: dict[str, Any],
    ) -> VoicePersona:
        if "name" in updates and updates["name"] is not None:
            persona.name = _clean_name(updates["name"])

        new_fields = {
            "tone": persona.tone,
            "style": persona.style,
            "point_of_view": persona.point_of_view,
            "constraints": persona.constraints,
        }
        for key in new_fields:
            if key in updates and updates[key] is not None:
                new_fields[key] = updates[key]
        normalized = _normalize_authoring_fields(**new_fields)
        persona.tone = normalized["tone"]
        persona.style = normalized["style"]
        persona.point_of_view = normalized["point_of_view"]
        persona.constraints = normalized["constraints"]

        if "session_id" in updates:
            persona.session_id = updates["session_id"]
            persona.scope = _scope_from_session(updates["session_id"])
        if "sort_order" in updates and updates["sort_order"] is not None:
            persona.sort_order = int(updates["sort_order"])
        if "enabled" in updates and updates["enabled"] is not None:
            persona.enabled = bool(updates["enabled"])

        await db.commit()
        await db.refresh(persona)
        return persona

    @classmethod
    async def delete_persona(cls, *, db: AsyncSession, persona: VoicePersona) -> None:
        await db.delete(persona)
        await db.commit()
