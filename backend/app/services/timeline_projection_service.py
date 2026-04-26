"""Chapter/order projections for relationship timeline events."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chapter import Chapter
from app.models.relationship import RelationshipTimelineEvent


@dataclass(frozen=True, slots=True)
class TimelinePoint:
    """Comparable chapter/order coordinate used by timeline projection."""

    chapter_number: int
    chapter_order: int


class TimelineProjectionService:
    """Projects append-only relationship, affiliation, and profession events."""

    def __init__(self, db: Session) -> None:
        self.db: Session = db

    def project_state(
        self,
        *,
        project_id: str,
        chapter_number: int,
        chapter_order: int | None = None,
    ) -> dict[str, list[RelationshipTimelineEvent]]:
        """Return active relationship/affiliation/profession rows at a story point."""

        order = chapter_order if chapter_order is not None else chapter_number
        return {
            "relationships": self.active_relationships(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_order=order,
            ),
            "affiliations": self.active_affiliations(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_order=order,
            ),
            "professions": self.active_professions(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_order=order,
            ),
        }

    def active_relationships(
        self,
        *,
        project_id: str,
        chapter_number: int,
        chapter_order: int | None = None,
    ) -> list[RelationshipTimelineEvent]:
        return self._active_events(
            project_id=project_id,
            event_type="relationship",
            chapter_number=chapter_number,
            chapter_order=chapter_order,
            key_fields=("relationship_id", "character_id", "related_character_id", "organization_entity_id"),
        )

    def active_affiliations(
        self,
        *,
        project_id: str,
        chapter_number: int,
        chapter_order: int | None = None,
    ) -> list[RelationshipTimelineEvent]:
        return self._active_events(
            project_id=project_id,
            event_type="affiliation",
            chapter_number=chapter_number,
            chapter_order=chapter_order,
            key_fields=("character_id",),
        )

    def active_professions(
        self,
        *,
        project_id: str,
        chapter_number: int,
        chapter_order: int | None = None,
    ) -> list[RelationshipTimelineEvent]:
        return self._active_events(
            project_id=project_id,
            event_type="profession",
            chapter_number=chapter_number,
            chapter_order=chapter_order,
            key_fields=("character_id",),
        )

    def history(
        self,
        *,
        project_id: str,
        event_type: str | None = None,
    ) -> list[RelationshipTimelineEvent]:
        """Return non-rolled-back timeline history sorted by valid-from point."""

        query = select(RelationshipTimelineEvent).where(
            RelationshipTimelineEvent.project_id == project_id,
            RelationshipTimelineEvent.event_status != "rolled_back",
        )
        if event_type is not None:
            query = query.where(RelationshipTimelineEvent.event_type == event_type)
        events = self.db.execute(query).scalars().all()
        return sorted(events, key=self._event_sort_key)

    def _active_events(
        self,
        *,
        project_id: str,
        event_type: str,
        chapter_number: int,
        chapter_order: int | None,
        key_fields: tuple[str, ...],
    ) -> list[RelationshipTimelineEvent]:
        point = TimelinePoint(chapter_number, chapter_order if chapter_order is not None else chapter_number)
        events = self.history(project_id=project_id, event_type=event_type)
        current: dict[tuple[Any, ...], RelationshipTimelineEvent] = {}
        for event in events:
            if event.event_status != "active" or not self._contains(event, point):
                continue
            key = tuple(getattr(event, field) for field in key_fields)
            existing = current.get(key)
            if existing is None or self._event_sort_key(existing) <= self._event_sort_key(event):
                current[key] = event
        return sorted(current.values(), key=self._event_sort_key)

    def _contains(self, event: RelationshipTimelineEvent, point: TimelinePoint) -> bool:
        start = self._point_for(event.valid_from_chapter_id, event.valid_from_chapter_order, default_start=True)
        end = self._point_for(event.valid_to_chapter_id, event.valid_to_chapter_order, default_start=False)
        assert start is not None
        return self._lte(start, point) and (end is None or self._lt(point, end))

    def _point_for(
        self,
        chapter_id: str | None,
        chapter_order: int | None,
        *,
        default_start: bool,
    ) -> TimelinePoint | None:
        if chapter_id is None:
            return TimelinePoint(-1_000_000, 0) if default_start else None
        chapter_number = self._chapter_number(chapter_id)
        if chapter_number is None:
            return TimelinePoint(-1_000_000, 0) if default_start else None
        return TimelinePoint(chapter_number, chapter_order if chapter_order is not None else chapter_number)

    @lru_cache(maxsize=512)
    def _chapter_number(self, chapter_id: str) -> int | None:
        chapter = self.db.get(Chapter, chapter_id)
        return None if chapter is None else int(chapter.chapter_number)

    def _event_sort_key(self, event: RelationshipTimelineEvent) -> tuple[int, int, str]:
        point = self._point_for(event.valid_from_chapter_id, event.valid_from_chapter_order, default_start=True)
        assert point is not None
        return (point.chapter_number, point.chapter_order, event.id)

    @staticmethod
    def _lt(left: TimelinePoint, right: TimelinePoint) -> bool:
        return (left.chapter_number, left.chapter_order) < (right.chapter_number, right.chapter_order)

    @staticmethod
    def _lte(left: TimelinePoint, right: TimelinePoint) -> bool:
        return (left.chapter_number, left.chapter_order) <= (right.chapter_number, right.chapter_order)


def project_timeline_state(
    db: Session,
    *,
    project_id: str,
    chapter_number: int,
    chapter_order: int | None = None,
) -> dict[str, list[RelationshipTimelineEvent]]:
    """Convenience wrapper for tests and future API handlers."""

    return TimelineProjectionService(db).project_state(
        project_id=project_id,
        chapter_number=chapter_number,
        chapter_order=chapter_order,
    )
