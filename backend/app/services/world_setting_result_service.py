"""Versioned world-setting result service.

Project.world_* columns remain the active snapshot. WorldSettingResult rows are
the reviewable generation/history records that can be accepted or rolled back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.relationship import WorldSettingResult


WORLD_RESULT_SOURCE_AI = "ai"

_WORLD_RESULT_RESPONSE_ATTRIBUTES = (
    "id",
    "project_id",
    "run_id",
    "status",
    "world_time_period",
    "world_location",
    "world_atmosphere",
    "world_rules",
    "prompt",
    "provider",
    "model",
    "reasoning_intensity",
    "raw_result",
    "source_type",
    "accepted_at",
    "accepted_by",
    "supersedes_result_id",
    "created_at",
    "updated_at",
)


@dataclass(slots=True)
class WorldSettingOperationResult:
    """Outcome for idempotent world-setting result operations."""

    result: WorldSettingResult
    changed: bool
    reason: str | None = None
    previous_result: WorldSettingResult | None = None

    def materialize_response_attributes(self) -> None:
        """Load response fields while a sync SQLAlchemy greenlet context is active."""

        self._materialize_result(self.result)
        self._materialize_result(self.previous_result)

    @staticmethod
    def _materialize_result(result: WorldSettingResult | None) -> None:
        if result is None:
            return
        for attribute_name in _WORLD_RESULT_RESPONSE_ATTRIBUTES:
            _ = getattr(result, attribute_name)


class WorldSettingResultService:
    """Creates and applies reviewable world-setting result snapshots."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_pending_result(
        self,
        *,
        project_id: str,
        world_time_period: str | None = None,
        world_location: str | None = None,
        world_atmosphere: str | None = None,
        world_rules: str | None = None,
        run_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        reasoning_intensity: str | None = None,
        prompt: str | None = None,
        prompt_version: str | None = None,
        template_version: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        actor_user_id: str | None = None,
        source_type: str = WORLD_RESULT_SOURCE_AI,
    ) -> WorldSettingResult:
        """Persist a generated draft without mutating Project.world_* fields."""

        project = self._require_project(project_id)
        result = WorldSettingResult(
            id=str(uuid.uuid4()),
            project_id=project.id,
            run_id=run_id,
            status="pending",
            world_time_period=world_time_period,
            world_location=world_location,
            world_atmosphere=world_atmosphere,
            world_rules=world_rules,
            prompt=prompt,
            provider=provider,
            model=model,
            reasoning_intensity=reasoning_intensity,
            raw_result=self._raw_result_payload(
                world_time_period=world_time_period,
                world_location=world_location,
                world_atmosphere=world_atmosphere,
                world_rules=world_rules,
                raw_payload=raw_payload,
                prompt_version=prompt_version,
                template_version=template_version,
                actor_user_id=actor_user_id,
            ),
            source_type=source_type,
            accepted_at=None,
            accepted_by=None,
        )
        self.db.add(result)
        self.db.flush()
        return result

    def accept_result(
        self,
        result_id: str,
        *,
        accepted_by: str | None = None,
        supersede_previous: bool = True,
    ) -> WorldSettingOperationResult:
        """Apply a result to Project.world_* and keep all history rows."""

        result = self._require_result(result_id)
        project = self._require_project(result.project_id)

        if result.status == "rejected":
            return WorldSettingOperationResult(result=result, changed=False, reason=f"result is {result.status}")

        changed = self._apply_snapshot(project, result)
        audit_changed = False
        if result.accepted_at is None:
            result.accepted_at = self._now()
            audit_changed = True
        if accepted_by is not None and result.accepted_by is None:
            result.accepted_by = accepted_by
            audit_changed = True

        previous = self._current_accepted_result(project_id=result.project_id, exclude_result_id=result.id)
        status_changed = result.status != "accepted"
        result.status = "accepted"

        if supersede_previous and previous is not None:
            if previous.status != "superseded":
                previous.status = "superseded"
                audit_changed = True
            if result.supersedes_result_id != previous.id:
                result.supersedes_result_id = previous.id
                audit_changed = True

        self.db.flush()
        return WorldSettingOperationResult(
            result=result,
            changed=changed or audit_changed or status_changed,
            previous_result=previous,
        )

    def reject_result(self, result_id: str) -> WorldSettingOperationResult:
        """Reject a pending draft without changing the active project snapshot."""

        result = self._require_result(result_id)
        if result.status == "rejected":
            return WorldSettingOperationResult(result=result, changed=False, reason="already rejected")
        if result.status in {"accepted", "superseded"}:
            return WorldSettingOperationResult(result=result, changed=False, reason=f"result is {result.status}")
        result.status = "rejected"
        self.db.flush()
        return WorldSettingOperationResult(result=result, changed=True)

    def rollback_result(
        self,
        result_id: str,
        *,
        actor_user_id: str | None = None,
    ) -> WorldSettingOperationResult:
        """Rollback the current accepted result by reapplying the prior accepted snapshot."""

        current = self._require_result(result_id)
        if current.status == "superseded":
            previous = self._previous_accepted_result(current)
            if previous is not None and previous.status == "accepted":
                return WorldSettingOperationResult(
                    result=current,
                    changed=False,
                    reason="already rolled back",
                    previous_result=previous,
                )
        if current.status != "accepted":
            return WorldSettingOperationResult(result=current, changed=False, reason=f"result is {current.status}")

        previous = self._previous_accepted_result(current)
        if previous is None:
            return WorldSettingOperationResult(result=current, changed=False, reason="no previous accepted result")

        project = self._require_project(current.project_id)
        changed = self._apply_snapshot(project, previous)
        previous_status_changed = previous.status != "accepted"
        previous.status = "accepted"
        if previous.accepted_at is None:
            previous.accepted_at = self._now()
            previous_status_changed = True
        if actor_user_id is not None and previous.accepted_by is None:
            previous.accepted_by = actor_user_id
            previous_status_changed = True

        current.status = "superseded"
        if current.supersedes_result_id is None:
            current.supersedes_result_id = previous.id
        operation_changed = changed or previous_status_changed or current.status == "superseded"
        self.db.flush()
        return WorldSettingOperationResult(
            result=current,
            changed=operation_changed,
            previous_result=previous,
        )

    def _require_project(self, project_id: str) -> Project:
        project = self.db.get(Project, project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        return project

    def _require_result(self, result_id: str) -> WorldSettingResult:
        result = self.db.get(WorldSettingResult, result_id)
        if result is None:
            raise ValueError(f"WorldSettingResult not found: {result_id}")
        return result

    def _current_accepted_result(self, *, project_id: str, exclude_result_id: str | None = None) -> WorldSettingResult | None:
        query = select(WorldSettingResult).where(
            WorldSettingResult.project_id == project_id,
            WorldSettingResult.status == "accepted",
        )
        if exclude_result_id is not None:
            query = query.where(WorldSettingResult.id != exclude_result_id)
        return self.db.execute(
            query.order_by(WorldSettingResult.accepted_at.desc(), WorldSettingResult.created_at.desc(), WorldSettingResult.id.desc())
        ).scalars().first()

    def _previous_accepted_result(self, current: WorldSettingResult) -> WorldSettingResult | None:
        if current.supersedes_result_id is not None:
            linked_previous = self.db.get(WorldSettingResult, current.supersedes_result_id)
            if (
                linked_previous is not None
                and linked_previous.project_id == current.project_id
                and linked_previous.status in {"accepted", "superseded"}
            ):
                return linked_previous

        query = select(WorldSettingResult).where(
            WorldSettingResult.project_id == current.project_id,
            WorldSettingResult.id != current.id,
            WorldSettingResult.accepted_at.is_not(None),
            WorldSettingResult.status.in_(["accepted", "superseded"]),
        )
        if current.accepted_at is not None:
            query = query.where(WorldSettingResult.accepted_at <= current.accepted_at)
        return self.db.execute(
            query.order_by(WorldSettingResult.accepted_at.desc(), WorldSettingResult.created_at.desc(), WorldSettingResult.id.desc())
        ).scalars().first()

    def _apply_snapshot(self, project: Project, result: WorldSettingResult) -> bool:
        changed = False
        fields = {
            "world_time_period": result.world_time_period,
            "world_location": result.world_location,
            "world_atmosphere": result.world_atmosphere,
            "world_rules": result.world_rules,
        }
        for field_name, value in fields.items():
            if getattr(project, field_name) != value:
                setattr(project, field_name, value)
                changed = True
        return changed

    def _raw_result_payload(
        self,
        *,
        world_time_period: str | None,
        world_location: str | None,
        world_atmosphere: str | None,
        world_rules: str | None,
        raw_payload: dict[str, Any] | None,
        prompt_version: str | None,
        template_version: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        payload = dict(raw_payload or {})
        payload.setdefault(
            "world_fields",
            {
                "world_time_period": world_time_period,
                "world_location": world_location,
                "world_atmosphere": world_atmosphere,
                "world_rules": world_rules,
            },
        )
        if prompt_version is not None:
            payload.setdefault("prompt_version", prompt_version)
        if template_version is not None:
            payload.setdefault("template_version", template_version)
        if actor_user_id is not None:
            payload.setdefault("created_by", actor_user_id)
        return payload

    def _now(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)


def create_pending_world_setting_result(db: Session, **kwargs: Any) -> WorldSettingResult:
    """Convenience wrapper for pending generation writes."""

    return WorldSettingResultService(db).create_pending_result(**kwargs)


def accept_world_setting_result(db: Session, result_id: str, **kwargs: Any) -> WorldSettingOperationResult:
    """Convenience wrapper for accepting/applying a result."""

    return WorldSettingResultService(db).accept_result(result_id, **kwargs)


def reject_world_setting_result(db: Session, result_id: str) -> WorldSettingOperationResult:
    """Convenience wrapper for rejecting a result."""

    return WorldSettingResultService(db).reject_result(result_id)


def rollback_world_setting_result(db: Session, result_id: str, **kwargs: Any) -> WorldSettingOperationResult:
    """Convenience wrapper for rolling back an accepted result."""

    return WorldSettingResultService(db).rollback_result(result_id, **kwargs)
