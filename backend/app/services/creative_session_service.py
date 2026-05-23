"""创作会话服务层。"""

# pyright: reportAny=false, reportExplicitAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.creative_session import CreativeSession, CreativeSessionMessage


class CreativeSessionService:
    """项目内创作会话业务逻辑。"""

    @staticmethod
    def session_dict(session: CreativeSession) -> dict[str, Any]:
        return {
            "id": session.id,
            "project_id": session.project_id,
            "user_id": session.user_id,
            "title": session.title,
            "status": session.status,
            "metadata": session.session_metadata,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    @staticmethod
    def message_dict(message: CreativeSessionMessage) -> dict[str, Any]:
        return {
            "id": message.id,
            "session_id": message.session_id,
            "project_id": message.project_id,
            "user_id": message.user_id,
            "role": message.role,
            "content": message.content,
            "position": message.position,
            "metadata": message.message_metadata,
            "created_at": message.created_at,
        }

    @classmethod
    async def create_session(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        title: str,
        metadata: dict[str, Any] | None = None,
    ) -> CreativeSession:
        session = CreativeSession(
            project_id=project_id,
            user_id=user_id,
            title=title.strip() or "未命名创作会话",
            session_metadata=metadata,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    @classmethod
    async def list_sessions(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
    ) -> list[CreativeSession]:
        result = await db.execute(
            select(CreativeSession)
            .where(CreativeSession.project_id == project_id, CreativeSession.user_id == user_id)
            .order_by(CreativeSession.updated_at.desc(), CreativeSession.created_at.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def get_session(
        cls,
        *,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> CreativeSession | None:
        result = await db.execute(
            select(CreativeSession).where(CreativeSession.id == session_id, CreativeSession.user_id == user_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    async def list_messages(
        cls,
        *,
        db: AsyncSession,
        session_id: str,
        user_id: str,
    ) -> list[CreativeSessionMessage]:
        result = await db.execute(
            select(CreativeSessionMessage)
            .where(CreativeSessionMessage.session_id == session_id, CreativeSessionMessage.user_id == user_id)
            .order_by(CreativeSessionMessage.position.asc(), CreativeSessionMessage.created_at.asc())
        )
        return list(result.scalars().all())

    @classmethod
    async def append_message(
        cls,
        *,
        db: AsyncSession,
        session: CreativeSession,
        user_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> CreativeSessionMessage:
        count_result = await db.execute(
            select(func.count(CreativeSessionMessage.id)).where(
                CreativeSessionMessage.session_id == session.id,
                CreativeSessionMessage.user_id == user_id,
            )
        )
        position = int(count_result.scalar_one() or 0)
        message = CreativeSessionMessage(
            session_id=session.id,
            project_id=session.project_id,
            user_id=user_id,
            role=role,
            content=content,
            position=position,
            message_metadata=metadata,
        )
        db.add(message)
        session.updated_at = func.now()
        await db.commit()
        await db.refresh(message)
        await db.refresh(session)
        return message

    @classmethod
    async def search_messages(
        cls,
        *,
        db: AsyncSession,
        project_id: str,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> list[tuple[CreativeSessionMessage, CreativeSession]]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        safe_limit = max(1, min(limit, 100))
        result = await db.execute(
            select(CreativeSessionMessage, CreativeSession)
            .join(CreativeSession, CreativeSession.id == CreativeSessionMessage.session_id)
            .where(
                CreativeSessionMessage.project_id == project_id,
                CreativeSessionMessage.user_id == user_id,
                CreativeSession.project_id == project_id,
                CreativeSession.user_id == user_id,
                func.lower(CreativeSessionMessage.content).like(f"%{normalized_query}%"),
            )
            .order_by(CreativeSessionMessage.created_at.asc(), CreativeSessionMessage.position.asc())
            .limit(safe_limit)
        )
        return [(message, session) for message, session in result.all()]
