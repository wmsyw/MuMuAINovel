"""Lorebook CRUD and deterministic selection service."""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lorebook import LorebookEntry


DEFAULT_CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class LorebookCandidate:
    """Pure selection input detached from ORM state."""

    id: str
    title: str
    content: str
    activation_keys: tuple[str, ...]
    priority: int = 0
    enabled: bool = True
    source_type: str = "manual"
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SelectedLorebookEntry:
    """Pure selection output for one entry."""

    id: str
    title: str
    priority: int
    matched_keys: tuple[str, ...]
    content: str
    source_type: str
    original_content_length: int
    trimmed: bool

    @property
    def selected_content_length(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class LorebookSelection:
    """Pure deterministic lorebook selection result."""

    total_candidates: int
    items: tuple[SelectedLorebookEntry, ...]
    chars_used: int
    budget_chars: int | None = None

    @property
    def selected_count(self) -> int:
        return len(self.items)


def _normalize_activation_keys(keys: Iterable[Any] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for key in keys or []:
        stripped = str(key).strip()
        folded = stripped.casefold()
        if stripped and folded not in seen:
            normalized.append(stripped)
            seen.add(folded)
    return tuple(normalized)


def _matched_keys(candidate: LorebookCandidate, activation_text: str) -> tuple[str, ...]:
    haystack = activation_text.casefold()
    if not haystack:
        return ()
    return tuple(key for key in candidate.activation_keys if key.casefold() in haystack)


def _first_match_index(keys: Sequence[str], activation_text: str) -> int:
    haystack = activation_text.casefold()
    positions = [haystack.find(key.casefold()) for key in keys]
    found = [position for position in positions if position >= 0]
    return min(found) if found else 1_000_000_000


def _effective_char_budget(
    *,
    max_chars: int | None,
    max_tokens: int | None,
    chars_per_token: int,
) -> int | None:
    budgets: list[int] = []
    if max_chars is not None:
        budgets.append(max_chars)
    if max_tokens is not None:
        budgets.append(max_tokens * chars_per_token)
    return min(budgets) if budgets else None


def _truncate_to_budget(content: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if len(content) <= budget:
        return content
    if budget == 1:
        return "…"
    return content[: budget - 1].rstrip() + "…"


def select_lorebook_entries(
    candidates: Sequence[LorebookCandidate],
    *,
    activation_text: str,
    max_chars: int | None = None,
    max_tokens: int | None = None,
    chars_per_token: int = DEFAULT_CHARS_PER_TOKEN,
) -> LorebookSelection:
    """Select enabled entries activated by keys, priority, and deterministic budget trimming.

    The function is intentionally pure: identical candidate fixtures and inputs always
    produce identical ordering and trimming, with no database or clock dependency.
    """

    safe_chars_per_token = max(1, chars_per_token)
    budget_chars = _effective_char_budget(
        max_chars=max_chars,
        max_tokens=max_tokens,
        chars_per_token=safe_chars_per_token,
    )

    activated: list[tuple[LorebookCandidate, tuple[str, ...]]] = []
    for candidate in candidates:
        if not candidate.enabled:
            continue
        keys = _normalize_activation_keys(candidate.activation_keys)
        normalized_candidate = LorebookCandidate(
            id=candidate.id,
            title=candidate.title,
            content=candidate.content,
            activation_keys=keys,
            priority=candidate.priority,
            enabled=candidate.enabled,
            source_type=candidate.source_type,
            created_at=candidate.created_at,
        )
        matches = _matched_keys(normalized_candidate, activation_text)
        if matches:
            activated.append((normalized_candidate, matches))

    activated.sort(
        key=lambda item: (
            -item[0].priority,
            _first_match_index(item[1], activation_text),
            item[0].title.casefold(),
            item[0].id,
        )
    )

    selected: list[SelectedLorebookEntry] = []
    chars_used = 0
    for candidate, matches in activated:
        remaining = None if budget_chars is None else budget_chars - chars_used
        if remaining is not None and remaining <= 0:
            break
        content = candidate.content.strip()
        if not content:
            continue
        selected_content = content if remaining is None else _truncate_to_budget(content, remaining)
        if not selected_content:
            break
        chars_used += len(selected_content)
        selected.append(
            SelectedLorebookEntry(
                id=candidate.id,
                title=candidate.title,
                priority=candidate.priority,
                matched_keys=matches,
                content=selected_content,
                source_type=candidate.source_type.strip() or "manual",
                original_content_length=len(content),
                trimmed=len(selected_content) < len(content),
            )
        )

    return LorebookSelection(
        total_candidates=len(candidates),
        items=tuple(selected),
        chars_used=chars_used,
        budget_chars=budget_chars,
    )


class LorebookService:
    """Async DB helpers for project-scoped lorebook entries."""

    @staticmethod
    def entry_dict(entry: LorebookEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "project_id": entry.project_id,
            "user_id": entry.user_id,
            "title": entry.title,
            "content": entry.content,
            "activation_keys": _normalize_activation_keys(entry.activation_keys),
            "priority": entry.priority,
            "enabled": bool(entry.enabled),
            "source_type": entry.source_type,
            "metadata": entry.entry_metadata,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }

    @staticmethod
    def selection_dict(selection: LorebookSelection) -> dict[str, Any]:
        return {
            "total_candidates": selection.total_candidates,
            "selected_count": selection.selected_count,
            "chars_used": selection.chars_used,
            "budget_chars": selection.budget_chars,
            "items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "priority": item.priority,
                    "order": order,
                    "source_type": "lorebook",
                    "entry_source_type": item.source_type,
                    "matched_keys": list(item.matched_keys),
                    "content": item.content,
                    "original_content_length": item.original_content_length,
                    "selected_content_length": item.selected_content_length,
                    "trimmed": item.trimmed,
                }
                for order, item in enumerate(selection.items, start=1)
            ],
        }

    @classmethod
    async def create_entry(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        title: str,
        content: str,
        activation_keys: Iterable[str] | None = None,
        priority: int = 0,
        enabled: bool = True,
        source_type: str = "manual",
        metadata: dict[str, Any] | None = None,
    ) -> LorebookEntry:
        entry = LorebookEntry(
            project_id=project_id,
            user_id=user_id,
            title=title.strip(),
            content=content.strip(),
            activation_keys=list(_normalize_activation_keys(activation_keys)),
            priority=priority,
            enabled=enabled,
            source_type=source_type.strip() or "manual",
            entry_metadata=metadata,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry

    @classmethod
    async def list_entries(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[LorebookEntry]]:
        filters = [LorebookEntry.project_id == project_id, LorebookEntry.user_id == user_id]
        if enabled is not None:
            filters.append(LorebookEntry.enabled == enabled)
        count_result = await db.execute(select(func.count(LorebookEntry.id)).where(*filters))
        result = await db.execute(
            select(LorebookEntry)
            .where(*filters)
            .order_by(LorebookEntry.priority.desc(), LorebookEntry.created_at.desc(), LorebookEntry.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return int(count_result.scalar_one() or 0), list(result.scalars().all())

    @classmethod
    async def get_entry(cls, *, db: AsyncSession, entry_id: str, user_id: str) -> LorebookEntry | None:
        result = await db.execute(
            select(LorebookEntry).where(LorebookEntry.id == entry_id, LorebookEntry.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def update_entry(
        cls,
        *,
        db: AsyncSession,
        entry: LorebookEntry,
        updates: dict[str, Any],
    ) -> LorebookEntry:
        field_map = {
            "title": "title",
            "content": "content",
            "activation_keys": "activation_keys",
            "priority": "priority",
            "enabled": "enabled",
            "source_type": "source_type",
            "metadata": "entry_metadata",
        }
        for source_field, model_field in field_map.items():
            if source_field not in updates:
                continue
            value = updates[source_field]
            if source_field == "activation_keys":
                value = list(_normalize_activation_keys(value))
            elif source_field in {"title", "content", "source_type"} and value is not None:
                value = str(value).strip()
            setattr(entry, model_field, value)
        await db.commit()
        await db.refresh(entry)
        return entry

    @classmethod
    async def delete_entry(cls, *, db: AsyncSession, entry: LorebookEntry) -> None:
        await db.delete(entry)
        await db.commit()

    @classmethod
    async def select_for_project(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        activation_text: str,
        max_chars: int | None = None,
        max_tokens: int | None = None,
        chars_per_token: int = DEFAULT_CHARS_PER_TOKEN,
    ) -> LorebookSelection:
        result = await db.execute(
            select(LorebookEntry)
            .where(LorebookEntry.project_id == project_id, LorebookEntry.user_id == user_id)
            .order_by(LorebookEntry.priority.desc(), LorebookEntry.created_at.desc(), LorebookEntry.id.desc())
        )
        entries = list(result.scalars().all())
        candidates = [
            LorebookCandidate(
                id=entry.id,
                title=entry.title,
                content=entry.content,
                activation_keys=_normalize_activation_keys(entry.activation_keys),
                priority=entry.priority,
                enabled=bool(entry.enabled),
                source_type=entry.source_type,
                created_at=entry.created_at,
            )
            for entry in entries
        ]
        return select_lorebook_entries(
            candidates,
            activation_text=activation_text,
            max_chars=max_chars,
            max_tokens=max_tokens,
            chars_per_token=chars_per_token,
        )
