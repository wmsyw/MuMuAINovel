"""Bounded group scene authoring service."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.group_scene import GROUP_SCENE_STATUS_DRAFT, GroupScene
from app.models.lorebook import LorebookEntry
from app.models.project import Project
from app.models.voice_persona import VoicePersona
from app.services.prompt_service import PromptService


MAX_GROUP_SCENE_PARTICIPANTS = 8
MAX_GROUP_SCENE_LORE_REFERENCES = 5


class GroupSceneValidationError(ValueError):
    """Raised when a group scene request leaves the writing-artifact boundary."""


def _clean_text(value: Any, *, max_chars: int, field_name: str) -> str:
    text = str(value or "").strip()
    if len(text) > max_chars:
        raise GroupSceneValidationError(f"{field_name}不能超过 {max_chars} 字符")
    return text


def _dedupe_ids(values: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in seen:
            _ = seen.add(item)
            result.append(item)
    return result


class GroupSceneService:
    """Create and list group scene drafts without chat-room/runtime semantics."""

    @staticmethod
    def scene_dict(scene: GroupScene) -> dict[str, Any]:
        return {
            "id": scene.id,
            "project_id": scene.project_id,
            "user_id": scene.user_id,
            "title": scene.title,
            "scenario": scene.scenario,
            "participant_character_ids": list(scene.participant_character_ids or []),
            "selected_voice_persona_id": scene.selected_voice_persona_id,
            "selected_lore_ids": list(scene.selected_lore_ids or []),
            "prompt_context": scene.prompt_context or "",
            "draft_text": scene.draft_text or "",
            "prompt_trace": dict(scene.prompt_trace or {}),
            "status": scene.status,
            "created_at": scene.created_at,
            "updated_at": scene.updated_at,
        }

    @staticmethod
    def _build_bounded_draft_scaffold(*, scenario: str, participants: list[Character], prompt_context: str) -> str:
        participant_names = [character.name for character in participants]
        lines = [
            "【群像场景草稿】",
            f"场景目标：{scenario}",
            f"参与角色：{'、'.join(participant_names)}",
        ]
        if prompt_context:
            lines.append(f"参考上下文：{prompt_context[:300]}")
        _ = lines.append("")
        lines.append("请在下列角色台词骨架中补写冲突、转折与潜台词：")
        for index, name in enumerate(participant_names, start=1):
            lines.append(f"{index}. {name}：……")
        _ = lines.append("")
        lines.append("（这是项目内写作草稿，不会写回章节，也不创建聊天房间或自动对话循环。）")
        return "\n".join(lines)

    @classmethod
    async def _load_participants(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        participant_character_ids: list[str],
    ) -> list[Character]:
        requested_ids = _dedupe_ids(participant_character_ids)
        if len(requested_ids) < 2:
            raise GroupSceneValidationError("群像场景至少需要两个项目角色")
        if len(requested_ids) > MAX_GROUP_SCENE_PARTICIPANTS:
            raise GroupSceneValidationError(f"群像场景最多选择 {MAX_GROUP_SCENE_PARTICIPANTS} 个角色")

        result = await db.execute(
            select(Character).where(
                Character.project_id == project_id,
                Character.id.in_(requested_ids),
            )
        )
        by_id = {character.id: character for character in result.scalars().all()}
        missing_ids = [character_id for character_id in requested_ids if character_id not in by_id]
        if missing_ids:
            raise GroupSceneValidationError("参与角色不存在或不属于当前项目")
        return [by_id[character_id] for character_id in requested_ids]

    @classmethod
    async def _load_voice_persona(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        persona_id: str | None,
    ) -> VoicePersona | None:
        if not persona_id:
            return None
        result = await db.execute(
            select(VoicePersona).where(
                VoicePersona.id == persona_id,
                VoicePersona.project_id == project_id,
                VoicePersona.user_id == user_id,
                VoicePersona.enabled == True,  # noqa: E712
            )
        )
        persona = result.scalar_one_or_none()
        if persona is None:
            raise GroupSceneValidationError("声音画像不存在、已停用或不属于当前项目")
        return persona

    @classmethod
    async def _load_lore_entries(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        lore_ids: list[str],
    ) -> list[LorebookEntry]:
        requested_ids = _dedupe_ids(lore_ids)
        if len(requested_ids) > MAX_GROUP_SCENE_LORE_REFERENCES:
            raise GroupSceneValidationError(f"群像场景最多引用 {MAX_GROUP_SCENE_LORE_REFERENCES} 条Lorebook")
        if not requested_ids:
            return []
        result = await db.execute(
            select(LorebookEntry).where(
                LorebookEntry.id.in_(requested_ids),
                LorebookEntry.project_id == project_id,
                LorebookEntry.user_id == user_id,
                LorebookEntry.enabled == True,  # noqa: E712
            )
        )
        by_id = {entry.id: entry for entry in result.scalars().all()}
        missing_ids = [entry_id for entry_id in requested_ids if entry_id not in by_id]
        if missing_ids:
            raise GroupSceneValidationError("Lorebook条目不存在、已停用或不属于当前项目")
        return [by_id[entry_id] for entry_id in requested_ids]

    @classmethod
    async def create_scene(
        cls,
        *,
        db: AsyncSession,
        project: Project,
        user_id: str,
        title: str,
        scenario: str,
        participant_character_ids: list[str],
        selected_voice_persona_id: str | None = None,
        selected_lore_ids: list[str] | None = None,
        prompt_context: str = "",
        draft_text: str | None = None,
    ) -> GroupScene:
        clean_title = _clean_text(title, max_chars=200, field_name="场景标题")
        clean_scenario = _clean_text(scenario, max_chars=4000, field_name="场景目标")
        clean_prompt_context = _clean_text(prompt_context, max_chars=4000, field_name="提示上下文")
        clean_draft_text = _clean_text(draft_text, max_chars=12000, field_name="场景草稿") if draft_text else ""
        if not clean_title:
            raise GroupSceneValidationError("场景标题不能为空")
        if not clean_scenario:
            raise GroupSceneValidationError("场景目标不能为空")

        participants = await cls._load_participants(db=db, project_id=project.id, participant_character_ids=participant_character_ids)
        voice_persona = await cls._load_voice_persona(db=db, project_id=project.id, user_id=user_id, persona_id=selected_voice_persona_id)
        lore_entries = await cls._load_lore_entries(db=db, project_id=project.id, user_id=user_id, lore_ids=selected_lore_ids or [])
        prompt_trace = PromptService.build_group_scene_prompt_trace(
            project=project,
            participants=participants,
            scenario=clean_scenario,
            voice_persona=voice_persona,
            lore_entries=lore_entries,
            prompt_context=clean_prompt_context,
        )
        final_draft_text = clean_draft_text or cls._build_bounded_draft_scaffold(
            scenario=clean_scenario,
            participants=participants,
            prompt_context=clean_prompt_context,
        )

        scene = GroupScene(
            project_id=project.id,
            user_id=user_id,
            title=clean_title,
            scenario=clean_scenario,
            participant_character_ids=[character.id for character in participants],
            selected_voice_persona_id=voice_persona.id if voice_persona else None,
            selected_lore_ids=[entry.id for entry in lore_entries],
            prompt_context=clean_prompt_context,
            draft_text=final_draft_text,
            prompt_trace=prompt_trace,
            status=GROUP_SCENE_STATUS_DRAFT,
        )
        db.add(scene)
        await db.commit()
        await db.refresh(scene)
        return scene

    @classmethod
    async def list_scenes(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[GroupScene]]:
        filters: list[Any] = [GroupScene.project_id == project_id, GroupScene.user_id == user_id]
        count_result = await db.execute(select(func.count(GroupScene.id)).where(*filters))
        result = await db.execute(
            select(GroupScene)
            .where(*filters)
            .order_by(GroupScene.updated_at.desc(), GroupScene.created_at.desc(), GroupScene.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return int(count_result.scalar_one() or 0), list(result.scalars().all())

    @classmethod
    async def get_scene(
        cls,
        *,
        db: AsyncSession,
        scene_id: str,
        user_id: str,
    ) -> GroupScene | None:
        result = await db.execute(select(GroupScene).where(GroupScene.id == scene_id, GroupScene.user_id == user_id))
        return result.scalar_one_or_none()

    @classmethod
    async def delete_scene(cls, *, db: AsyncSession, scene: GroupScene) -> None:
        await db.delete(scene)
        await db.commit()
