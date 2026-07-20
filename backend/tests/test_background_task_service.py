from __future__ import annotations

from typing import Any

import pytest

from app.services.background_task_service import TaskProgressTracker


@pytest.mark.asyncio
async def test_complete_without_result_does_not_clear_existing_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[dict[str, Any]] = []

    async def record_update(self: TaskProgressTracker, **kwargs: Any) -> None:
        updates.append(kwargs)

    monkeypatch.setattr(TaskProgressTracker, "_update_task", record_update)
    tracker = TaskProgressTracker("task-payload", "user-payload", "payload")

    await tracker.complete("完成但没有新结果")
    assert "task_result" not in updates[-1]

    await tracker.complete("完成并写入结果", result={"value": 1})
    assert updates[-1]["task_result"] == {"value": 1}
