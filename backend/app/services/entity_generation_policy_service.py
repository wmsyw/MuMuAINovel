"""Central policy gate for AI-created canonical story entities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.relationship import EntityProvenance
from app.models.settings import Settings


EntityType = Literal["character", "organization", "career"]
ActionType = Literal[
    "ai_generation",
    "auto_create",
    "manual_create",
    "manual_edit",
    "candidate_promotion",
]

MANUAL_ACTIONS: set[str] = {"manual_create", "manual_edit"}
RESTRICTED_AI_ACTIONS: set[str] = {"ai_generation", "auto_create", "candidate_promotion"}
POLICY_OVERRIDE_SOURCE_TYPE = "ai_generation_policy_override"


@dataclass(frozen=True)
class EntityGenerationPolicyInput:
    """Explicit inputs required to decide canonical entity generation policy."""

    actor_user_id: str | None
    project_id: str
    entity_type: EntityType
    source_endpoint: str
    action_type: ActionType
    is_admin: bool = False
    allow_ai_entity_generation: bool = False
    provider: str | None = None
    model: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class EntityGenerationPolicyDecision:
    """Deterministic result returned by the central entity generation policy gate."""

    allowed: bool
    mode: Literal["canonical_allowed", "candidate_only", "manual_allowed"]
    code: str
    message: str
    audit_required: bool
    override_source: Literal["admin", "advanced_setting", "manual", "none"]
    policy_input: EntityGenerationPolicyInput

    def to_response(self) -> dict[str, Any]:
        """Stable payload for route/SSE responses and tests."""
        return {
            "policy_gate": "entity_generation",
            "allowed": self.allowed,
            "mode": self.mode,
            "code": self.code,
            "message": self.message,
            "audit_required": self.audit_required,
            "override_source": self.override_source,
            "entity_type": self.policy_input.entity_type,
            "action_type": self.policy_input.action_type,
            "source_endpoint": self.policy_input.source_endpoint,
            "project_id": self.policy_input.project_id,
            "actor_user_id": self.policy_input.actor_user_id,
            "provider": self.policy_input.provider,
            "model": self.policy_input.model,
            "reason": self.policy_input.reason,
        }


class EntityGenerationPolicyService:
    """Backend-enforced gate for canonical Character/OrganizationEntity/Career creation."""

    async def get_allow_ai_entity_generation(self, db: AsyncSession, actor_user_id: str | None) -> bool:
        """Load the persisted advanced override flag for the actor; missing settings default to false."""
        if not actor_user_id:
            return False
        result = await db.execute(select(Settings).where(Settings.user_id == actor_user_id))
        user_settings = result.scalar_one_or_none()
        return bool(user_settings and user_settings.allow_ai_entity_generation)

    def get_allow_ai_entity_generation_sync(self, db: Session, actor_user_id: str | None) -> bool:
        """Synchronous variant used by focused service tests."""
        if not actor_user_id:
            return False
        user_settings = db.execute(select(Settings).where(Settings.user_id == actor_user_id)).scalar_one_or_none()
        return bool(user_settings and user_settings.allow_ai_entity_generation)

    def evaluate(self, policy_input: EntityGenerationPolicyInput) -> EntityGenerationPolicyDecision:
        """Decide whether a canonical entity mutation is allowed."""
        action = policy_input.action_type
        if action in MANUAL_ACTIONS:
            return EntityGenerationPolicyDecision(
                allowed=True,
                mode="manual_allowed",
                code="manual_entity_action_allowed",
                message="手动创建/编辑实体不受 AI 生成策略限制。",
                audit_required=False,
                override_source="manual",
                policy_input=policy_input,
            )

        if action not in RESTRICTED_AI_ACTIONS:
            return EntityGenerationPolicyDecision(
                allowed=False,
                mode="candidate_only",
                code="unknown_entity_generation_action",
                message=f"未知实体生成动作：{action}",
                audit_required=False,
                override_source="none",
                policy_input=policy_input,
            )

        if policy_input.is_admin:
            return EntityGenerationPolicyDecision(
                allowed=True,
                mode="canonical_allowed",
                code="admin_entity_generation_override",
                message="管理员覆盖允许 AI 生成规范实体。",
                audit_required=True,
                override_source="admin",
                policy_input=policy_input,
            )

        if policy_input.allow_ai_entity_generation:
            return EntityGenerationPolicyDecision(
                allowed=True,
                mode="canonical_allowed",
                code="advanced_entity_generation_override",
                message="用户高级设置允许 AI 生成规范实体。",
                audit_required=True,
                override_source="advanced_setting",
                policy_input=policy_input,
            )

        return EntityGenerationPolicyDecision(
            allowed=False,
            mode="candidate_only",
            code="ai_entity_generation_disabled",
            message=(
                "AI 直接生成规范角色、组织或职业已被后端策略阻止；"
                "请通过候选评审/手动创建流程入库，或由管理员/高级设置启用覆盖。"
            ),
            audit_required=False,
            override_source="none",
            policy_input=policy_input,
        )

    async def evaluate_for_user(
        self,
        db: AsyncSession,
        *,
        actor_user_id: str | None,
        project_id: str,
        entity_type: EntityType,
        source_endpoint: str,
        action_type: ActionType,
        is_admin: bool = False,
        provider: str | None = None,
        model: str | None = None,
        reason: str | None = None,
    ) -> EntityGenerationPolicyDecision:
        """Load persisted settings and evaluate policy for an async route/service path."""
        allow_ai_entity_generation = await self.get_allow_ai_entity_generation(db, actor_user_id)
        return self.evaluate(
            EntityGenerationPolicyInput(
                actor_user_id=actor_user_id,
                project_id=project_id,
                entity_type=entity_type,
                source_endpoint=source_endpoint,
                action_type=action_type,
                is_admin=is_admin,
                allow_ai_entity_generation=allow_ai_entity_generation,
                provider=provider,
                model=model,
                reason=reason,
            )
        )

    def record_override_audit(
        self,
        db: Session | AsyncSession,
        decision: EntityGenerationPolicyDecision,
        resulting_canonical_ids: Iterable[str],
        *,
        extra_payload: dict[str, Any] | None = None,
    ) -> list[EntityProvenance]:
        """Persist audit metadata for allowed AI canonical creation/promotions.

        Uses the existing EntityProvenance JSON payload to avoid schema churn. The
        caller owns flush/commit so this method can be used in route transactions.
        """
        canonical_ids = [entity_id for entity_id in resulting_canonical_ids if entity_id]
        if not decision.allowed or not decision.audit_required or not canonical_ids:
            return []

        policy_input = decision.policy_input
        claim_payload: dict[str, Any] = {
            "policy_gate": "entity_generation",
            "decision_code": decision.code,
            "override_source": decision.override_source,
            "actor_user_id": policy_input.actor_user_id,
            "project_id": policy_input.project_id,
            "entity_type": policy_input.entity_type,
            "source_endpoint": policy_input.source_endpoint,
            "action_type": policy_input.action_type,
            "provider": policy_input.provider,
            "model": policy_input.model,
            "reason": policy_input.reason,
            "resulting_canonical_ids": canonical_ids,
        }
        if extra_payload:
            claim_payload.update(extra_payload)

        rows: list[EntityProvenance] = []
        for canonical_id in canonical_ids:
            audit_row = EntityProvenance(
                project_id=policy_input.project_id,
                entity_type=policy_input.entity_type,
                entity_id=canonical_id,
                source_type=POLICY_OVERRIDE_SOURCE_TYPE,
                source_id=None,
                claim_type=f"{policy_input.action_type}_override",
                claim_payload=claim_payload,
                evidence_text=policy_input.reason,
                confidence=1.0,
                status="active",
                created_by=policy_input.actor_user_id,
            )
            db.add(audit_row)
            rows.append(audit_row)
        return rows


entity_generation_policy_service = EntityGenerationPolicyService()
