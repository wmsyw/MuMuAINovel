"""金手指管理服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.goldfinger import GOLDFINGER_STATUSES, Goldfinger, GoldfingerHistoryEvent
from app.schemas.goldfinger import GOLDFINGER_PAYLOAD_VERSION, GoldfingerImportPayload


JSON_FIELD_ATTRS: dict[str, str] = {
    "rules": "rules",
    "tasks": "tasks",
    "rewards": "rewards",
    "limits": "limits",
    "trigger_conditions": "trigger_conditions",
    "cooldown": "cooldown",
    "aliases": "aliases",
    "metadata": "goldfinger_metadata",
}

MUTABLE_FIELDS: tuple[str, ...] = (
    "name",
    "owner_character_id",
    "owner_character_name",
    "type",
    "status",
    "summary",
    "rules",
    "tasks",
    "rewards",
    "limits",
    "trigger_conditions",
    "cooldown",
    "aliases",
    "metadata",
    "confidence",
    "last_source_chapter_id",
)


class GoldfingerService:
    """金手指 CRUD、历史与导入导出服务。"""

    @staticmethod
    def normalized_name(value: str | None) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def response_dict(goldfinger: Goldfinger) -> dict[str, Any]:
        return {
            "id": goldfinger.id,
            "project_id": goldfinger.project_id,
            "name": goldfinger.name,
            "normalized_name": goldfinger.normalized_name,
            "owner_character_id": goldfinger.owner_character_id,
            "owner_character_name": goldfinger.owner_character_name,
            "type": goldfinger.type,
            "status": goldfinger.status,
            "summary": goldfinger.summary,
            "rules": goldfinger.rules,
            "tasks": goldfinger.tasks,
            "rewards": goldfinger.rewards,
            "limits": goldfinger.limits,
            "trigger_conditions": goldfinger.trigger_conditions,
            "cooldown": goldfinger.cooldown,
            "aliases": goldfinger.aliases,
            "metadata": goldfinger.goldfinger_metadata,
            "created_at": goldfinger.created_at,
            "updated_at": goldfinger.updated_at,
            "created_by": goldfinger.created_by,
            "updated_by": goldfinger.updated_by,
            "source": goldfinger.source,
            "confidence": goldfinger.confidence,
            "last_source_chapter_id": goldfinger.last_source_chapter_id,
        }

    @staticmethod
    def export_item(goldfinger: Goldfinger) -> dict[str, Any]:
        item = GoldfingerService.response_dict(goldfinger)
        item["created_at"] = goldfinger.created_at.isoformat() if goldfinger.created_at else None
        item["updated_at"] = goldfinger.updated_at.isoformat() if goldfinger.updated_at else None
        item.pop("project_id", None)
        item.pop("normalized_name", None)
        item.pop("created_by", None)
        item.pop("updated_by", None)
        item.pop("source", None)
        return item

    @staticmethod
    def history_dict(event: GoldfingerHistoryEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "goldfinger_id": event.goldfinger_id,
            "project_id": event.project_id,
            "chapter_id": event.chapter_id,
            "event_type": event.event_type,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "evidence_excerpt": event.evidence_excerpt,
            "confidence": event.confidence,
            "source_type": event.source_type,
            "created_at": event.created_at,
        }

    @staticmethod
    async def list_goldfingers(project_id: str, db: AsyncSession) -> list[Goldfinger]:
        result = await db.execute(
            select(Goldfinger)
            .where(Goldfinger.project_id == project_id)
            .order_by(Goldfinger.created_at.desc(), Goldfinger.name.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_goldfinger(goldfinger_id: str, db: AsyncSession) -> Goldfinger | None:
        result = await db.execute(select(Goldfinger).where(Goldfinger.id == goldfinger_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_goldfinger(
        *,
        project_id: str,
        data: dict[str, Any],
        user_id: str,
        db: AsyncSession,
        source: str = "manual",
        history_source_type: str = "manual",
        commit: bool = True,
    ) -> Goldfinger:
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("金手指名称不能为空")

        normalized = GoldfingerService.normalized_name(name)
        existing = await GoldfingerService.find_by_normalized_name(project_id, normalized, db)
        if existing:
            raise ValueError("同名金手指已存在")

        status = data.get("status") or "unknown"
        GoldfingerService._validate_status(status)
        owner_id, owner_name = await GoldfingerService._resolve_owner_snapshot(
            db=db,
            project_id=project_id,
            owner_character_id=data.get("owner_character_id"),
            owner_character_name=data.get("owner_character_name"),
        )

        goldfinger = Goldfinger(
            project_id=project_id,
            name=name,
            normalized_name=normalized,
            owner_character_id=owner_id,
            owner_character_name=owner_name,
            type=data.get("type"),
            status=status,
            summary=data.get("summary"),
            created_by=user_id,
            updated_by=user_id,
            source=source,
            confidence=data.get("confidence"),
            last_source_chapter_id=data.get("last_source_chapter_id"),
        )
        GoldfingerService._apply_json_fields(goldfinger, data)
        db.add(goldfinger)
        await db.flush()
        GoldfingerService.add_history_event(
            db,
            goldfinger=goldfinger,
            event_type="created" if history_source_type == "manual" else "imported",
            old_value=None,
            new_value=GoldfingerService.response_dict(goldfinger),
            source_type=history_source_type,
            chapter_id=goldfinger.last_source_chapter_id,
            evidence_excerpt=data.get("evidence_excerpt"),
            confidence=goldfinger.confidence,
        )
        if commit:
            await db.commit()
            await db.refresh(goldfinger)
        return goldfinger

    @staticmethod
    async def update_goldfinger(
        *,
        goldfinger: Goldfinger,
        data: dict[str, Any],
        user_id: str,
        db: AsyncSession,
    ) -> Goldfinger:
        old_snapshot = GoldfingerService.response_dict(goldfinger)

        if "name" in data and data["name"] is not None:
            name = str(data["name"]).strip()
            if not name:
                raise ValueError("金手指名称不能为空")
            normalized = GoldfingerService.normalized_name(name)
            existing = await GoldfingerService.find_by_normalized_name(goldfinger.project_id, normalized, db)
            if existing and existing.id != goldfinger.id:
                raise ValueError("同名金手指已存在")
            goldfinger.name = name
            goldfinger.normalized_name = normalized

        if "status" in data and data["status"] is not None:
            GoldfingerService._validate_status(data["status"])
            goldfinger.status = data["status"]

        if "owner_character_id" in data:
            owner_id, owner_name = await GoldfingerService._resolve_owner_snapshot(
                db=db,
                project_id=goldfinger.project_id,
                owner_character_id=data.get("owner_character_id"),
                owner_character_name=data.get("owner_character_name"),
            )
            goldfinger.owner_character_id = owner_id
            goldfinger.owner_character_name = owner_name
        elif "owner_character_name" in data:
            goldfinger.owner_character_name = data.get("owner_character_name")

        for field in ("type", "summary", "confidence", "last_source_chapter_id"):
            if field in data:
                setattr(goldfinger, field, data[field])
        GoldfingerService._apply_json_fields(goldfinger, data)
        goldfinger.updated_by = user_id

        new_snapshot = GoldfingerService.response_dict(goldfinger)
        old_changed: dict[str, Any] = {}
        new_changed: dict[str, Any] = {}
        for field in MUTABLE_FIELDS:
            if old_snapshot.get(field) != new_snapshot.get(field):
                old_changed[field] = old_snapshot.get(field)
                new_changed[field] = new_snapshot.get(field)

        if old_changed:
            GoldfingerService.add_history_event(
                db,
                goldfinger=goldfinger,
                event_type="updated",
                old_value=old_changed,
                new_value=new_changed,
                source_type="manual",
                chapter_id=goldfinger.last_source_chapter_id,
                evidence_excerpt=data.get("evidence_excerpt"),
                confidence=goldfinger.confidence,
            )
        await db.commit()
        await db.refresh(goldfinger)
        return goldfinger

    @staticmethod
    async def delete_goldfinger(goldfinger: Goldfinger, db: AsyncSession) -> None:
        await db.delete(goldfinger)
        await db.commit()

    @staticmethod
    async def list_history(goldfinger_id: str, db: AsyncSession) -> list[GoldfingerHistoryEvent]:
        result = await db.execute(
            select(GoldfingerHistoryEvent)
            .where(GoldfingerHistoryEvent.goldfinger_id == goldfinger_id)
            .order_by(GoldfingerHistoryEvent.created_at.asc(), GoldfingerHistoryEvent.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def export_project(project_id: str, db: AsyncSession) -> dict[str, Any]:
        goldfingers = await GoldfingerService.list_goldfingers(project_id, db)
        return {
            "version": GOLDFINGER_PAYLOAD_VERSION,
            "export_time": datetime.utcnow().isoformat(),
            "export_type": "goldfingers",
            "project_id": project_id,
            "count": len(goldfingers),
            "data": [GoldfingerService.export_item(row) for row in goldfingers],
        }

    @staticmethod
    async def dry_run_import(
        *,
        project_id: str,
        payload: GoldfingerImportPayload,
        db: AsyncSession,
    ) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        would_create: list[dict[str, Any]] = []

        if payload.version != GOLDFINGER_PAYLOAD_VERSION:
            errors.append({
                "index": None,
                "name": None,
                "message": f"版本错误: 期望 {GOLDFINGER_PAYLOAD_VERSION}，实际 {payload.version or '缺失'}",
            })
        if payload.export_type not in (None, "goldfingers"):
            errors.append({
                "index": None,
                "name": None,
                "message": f"导出类型错误: 期望 goldfingers，实际 {payload.export_type}",
            })
        if payload.count is not None and payload.count != len(payload.data):
            warnings.append({
                "index": None,
                "name": None,
                "message": f"count={payload.count} 与 data 数量 {len(payload.data)} 不一致",
            })

        seen: dict[str, int] = {}
        normalized_names: list[str] = []
        for idx, item in enumerate(payload.data):
            name = str(item.name or "").strip()
            normalized = GoldfingerService.normalized_name(name)
            if not name:
                errors.append({"index": idx, "name": item.name, "message": "缺少 name 字段"})
                continue
            status = item.status or "unknown"
            if status not in GOLDFINGER_STATUSES:
                errors.append({"index": idx, "name": name, "message": f"状态无效: {status}"})
            if normalized in seen:
                conflicts.append({
                    "index": idx,
                    "name": name,
                    "normalized_name": normalized,
                    "existing_id": None,
                    "reason": f"payload_duplicate:{seen[normalized]}",
                })
            else:
                seen[normalized] = idx
                normalized_names.append(normalized)

        if normalized_names:
            existing_result = await db.execute(
                select(Goldfinger).where(
                    Goldfinger.project_id == project_id,
                    Goldfinger.normalized_name.in_(normalized_names),
                )
            )
            existing_by_name = {row.normalized_name: row for row in existing_result.scalars().all()}
            for idx, item in enumerate(payload.data):
                name = str(item.name or "").strip()
                normalized = GoldfingerService.normalized_name(name)
                existing = existing_by_name.get(normalized)
                if existing:
                    conflicts.append({
                        "index": idx,
                        "name": name,
                        "normalized_name": normalized,
                        "existing_id": existing.id,
                        "reason": "normalized_name_conflict",
                    })

        conflict_indexes = {int(conflict["index"]) for conflict in conflicts if conflict.get("index") is not None}
        error_indexes = {int(error["index"]) for error in errors if error.get("index") is not None}
        for idx, item in enumerate(payload.data):
            if idx in conflict_indexes or idx in error_indexes:
                continue
            name = str(item.name or "").strip()
            if not name:
                continue
            would_create.append({
                "index": idx,
                "name": name,
                "normalized_name": GoldfingerService.normalized_name(name),
            })

        return {
            "valid": len(errors) == 0 and len(conflicts) == 0,
            "version": payload.version,
            "expected_version": GOLDFINGER_PAYLOAD_VERSION,
            "total": len(payload.data),
            "creatable": len(would_create),
            "conflicts": conflicts,
            "errors": errors,
            "warnings": warnings,
            "would_create": would_create,
            "statistics": {
                "total": len(payload.data),
                "creatable": len(would_create),
                "conflicts": len(conflicts),
                "errors": len(errors),
            },
        }

    @staticmethod
    async def import_project(
        *,
        project_id: str,
        payload: GoldfingerImportPayload,
        user_id: str,
        db: AsyncSession,
    ) -> dict[str, Any]:
        dry_run = await GoldfingerService.dry_run_import(project_id=project_id, payload=payload, db=db)
        if not dry_run["valid"]:
            return {
                "success": False,
                "message": "导入前验证失败，未写入任何金手指",
                "imported": 0,
                "imported_ids": [],
                "dry_run": dry_run,
                "warnings": dry_run["warnings"],
            }

        imported: list[Goldfinger] = []
        try:
            for item in payload.data:
                item_data = item.model_dump(exclude_unset=True)
                item_data["status"] = item_data.get("status") or "unknown"
                goldfinger = await GoldfingerService.create_goldfinger(
                    project_id=project_id,
                    data=item_data,
                    user_id=user_id,
                    db=db,
                    source="imported",
                    history_source_type="import",
                    commit=False,
                )
                imported.append(goldfinger)
            await db.commit()
            for goldfinger in imported:
                await db.refresh(goldfinger)
        except Exception:
            await db.rollback()
            raise

        return {
            "success": True,
            "message": f"成功导入 {len(imported)} 个金手指",
            "imported": len(imported),
            "imported_ids": [row.id for row in imported],
            "dry_run": dry_run,
            "warnings": dry_run["warnings"],
        }

    @staticmethod
    async def find_by_normalized_name(project_id: str, normalized_name: str, db: AsyncSession) -> Goldfinger | None:
        result = await db.execute(
            select(Goldfinger).where(
                Goldfinger.project_id == project_id,
                Goldfinger.normalized_name == normalized_name,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def add_history_event(
        db: AsyncSession,
        *,
        goldfinger: Goldfinger,
        event_type: str,
        old_value: Any | None,
        new_value: Any | None,
        source_type: str,
        chapter_id: str | None = None,
        evidence_excerpt: str | None = None,
        confidence: float | None = None,
    ) -> GoldfingerHistoryEvent:
        event = GoldfingerHistoryEvent(
            goldfinger_id=goldfinger.id,
            project_id=goldfinger.project_id,
            chapter_id=chapter_id,
            event_type=event_type,
            old_value=GoldfingerService._json_safe(old_value),
            new_value=GoldfingerService._json_safe(new_value),
            evidence_excerpt=evidence_excerpt,
            confidence=confidence,
            source_type=source_type,
        )
        db.add(event)
        return event

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in GOLDFINGER_STATUSES:
            raise ValueError(f"金手指状态无效: {status}")

    @staticmethod
    def _apply_json_fields(goldfinger: Goldfinger, data: dict[str, Any]) -> None:
        for field, attr in JSON_FIELD_ATTRS.items():
            if field in data:
                setattr(goldfinger, attr, data[field])

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: GoldfingerService._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [GoldfingerService._json_safe(item) for item in value]
        return value

    @staticmethod
    async def _resolve_owner_snapshot(
        *,
        db: AsyncSession,
        project_id: str,
        owner_character_id: str | None,
        owner_character_name: str | None,
    ) -> tuple[str | None, str | None]:
        if not owner_character_id:
            return None, owner_character_name
        result = await db.execute(
            select(Character).where(
                Character.id == owner_character_id,
                Character.project_id == project_id,
            )
        )
        owner = result.scalar_one_or_none()
        if not owner:
            raise ValueError("拥有者角色不存在或不属于当前项目")
        return owner.id, owner.name
