"""灵感模式API - 通过对话引导创建项目"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Literal, TypeVar, Optional, List
import json
from uuid import uuid4

from app.database import get_db
from app.services.ai_service import AIService
from app.services.json_helper import clean_json_response, loads_json
from app.api.settings import get_user_ai_service
from app.services.prompt_service import PromptService
from app.logger import get_logger

router = APIRouter(prefix="/inspiration", tags=["灵感模式"])
logger = get_logger(__name__)

INSPIRATION_STRUCTURED_OUTPUT_INVALID = "INSPIRATION_STRUCTURED_OUTPUT_INVALID"
TBaseModel = TypeVar("TBaseModel", bound=BaseModel)


InspirationStep = Literal[
    "title",
    "description",
    "theme",
    "genre",
    "world_setting",
    "core_conflict",
    "protagonist",
    "golden_finger",
    "auto",
]

QualityDimension = Literal[
    "novelty",
    "writability",
    "commercial_hook",
    "consistency",
    "long_form_potential",
]


class InspirationOptionsRequest(BaseModel):
    """灵感选项生成请求。"""

    step: InspirationStep = Field(default="title", description="灵感AI生成步骤")
    context: Dict[str, Any] = Field(default_factory=dict, description="已收集的上下文")

    model_config = ConfigDict(extra="allow")


class InspirationRefineOptionsRequest(InspirationOptionsRequest):
    """灵感选项反馈重生成请求。"""

    feedback: str = Field(..., description="用户反馈")
    previous_options: list[str] = Field(default_factory=list, description="上一轮选项")


class InspirationOptionsResponse(BaseModel):
    """灵感选项生成响应，兼容旧的prompt/options结构。"""

    prompt: str | None = None
    options: list[str] = Field(default_factory=list)
    error: str | None = None


class InspirationQuickGenerateRequest(BaseModel):
    """灵感模式智能补全请求。"""

    title: str | None = None
    description: str | None = None
    theme: str | None = None
    genre: str | list[str] | None = None

    model_config = ConfigDict(extra="allow")


class InspirationQuickGenerateResponse(BaseModel):
    """灵感模式智能补全响应。"""

    title: str | None = None
    description: str | None = None
    theme: str | None = None
    genre: list[str] | None = None
    narrative_perspective: str | None = None
    error: str | None = None


class InspirationDirectionCard(BaseModel):
    """故事方向卡片草稿契约。"""

    id: str
    title: str
    hook: str
    genre: list[str]
    world_setting: str
    core_conflict: str
    protagonist: str
    golden_finger: str | None = None
    opening_hook: str
    selling_points: list[str]
    risks: list[str]

    @field_validator(
        "id",
        "title",
        "hook",
        "world_setting",
        "core_conflict",
        "protagonist",
        "opening_hook",
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("字段必须是非空字符串")
        return value.strip()

    @field_validator("genre", "selling_points", "risks")
    @classmethod
    def _required_string_list(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("字段必须是非空字符串数组")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("数组项必须是非空字符串")
            normalized.append(item.strip())
        return normalized

    @field_validator("golden_finger")
    @classmethod
    def _optional_golden_finger(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("golden_finger必须是字符串、空字符串或null")
        return value.strip()


GUIDANCE_TAG_LIMIT = 5
GUIDANCE_TAG_MAX_LENGTH = 30
GUIDANCE_PLOT_BRIEF_MAX_LENGTH = 500


def _sanitize_guidance_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    return text[:max_length]


class InspirationGuidance(BaseModel):
    channel: Optional[str] = None
    genre: Optional[str] = None
    themes: Optional[List[str]] = None
    characters: Optional[List[str]] = None
    plots: Optional[List[str]] = None
    plot_brief: Optional[str] = None

    model_config = ConfigDict(extra="ignore")

    @field_validator("channel", "genre")
    @classmethod
    def _sanitize_short_label(cls, value: Optional[str]) -> Optional[str]:
        return _sanitize_guidance_text(value, GUIDANCE_TAG_MAX_LENGTH)

    @field_validator("themes", "characters", "plots")
    @classmethod
    def _sanitize_tag_list(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return None

        normalized: list[str] = []
        for item in value:
            text = _sanitize_guidance_text(item, GUIDANCE_TAG_MAX_LENGTH)
            if not text:
                continue
            normalized.append(text)
            if len(normalized) >= GUIDANCE_TAG_LIMIT:
                break

        return normalized or None

    @field_validator("plot_brief")
    @classmethod
    def _sanitize_plot_brief(cls, value: Optional[str]) -> Optional[str]:
        return _sanitize_guidance_text(value, GUIDANCE_PLOT_BRIEF_MAX_LENGTH)

    def has_content(self) -> bool:
        return any(
            (
                self.channel,
                self.genre,
                self.themes,
                self.characters,
                self.plots,
                self.plot_brief,
            )
        )


class InspirationGenerateCardsRequest(BaseModel):
    """故事方向卡片生成请求契约。"""

    idea: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    card_count: int = Field(default=3, ge=1, le=10)
    guidance: Optional[InspirationGuidance] = None

    @field_validator("idea")
    @classmethod
    def _sanitize_idea(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def _require_idea_or_guidance(self) -> "InspirationGenerateCardsRequest":
        if self.idea:
            return self
        if self.guidance and self.guidance.has_content():
            self.idea = _synthesize_idea_from_guidance(self.guidance)
        if not self.idea:
            raise ValueError("idea 或 guidance 至少需要提供一个非空内容")
        return self


def _synthesize_idea_from_guidance(guidance: InspirationGuidance) -> str:
    parts: list[str] = []
    if guidance.channel:
        parts.append(f"{guidance.channel}频道")
    if guidance.genre:
        parts.append(guidance.genre)
    if guidance.themes:
        parts.append("主题" + "、".join(guidance.themes))
    if guidance.characters:
        parts.append("角色" + "、".join(guidance.characters))
    if guidance.plots:
        parts.append("情节" + "、".join(guidance.plots))
    if guidance.plot_brief:
        parts.append(guidance.plot_brief)

    if not parts:
        return ""
    return "基于这些灵感标签创作故事：" + "；".join(parts)


def build_inspiration_guidance_prompt(guidance: InspirationGuidance | None) -> str:
    if guidance is None or not guidance.has_content():
        return ""

    lines: list[str] = []
    if guidance.channel:
        lines.append(f"题材频道：{guidance.channel}")
    if guidance.genre:
        lines.append(f"类型标签：{guidance.genre}")
    if guidance.themes:
        lines.append(f"主题标签：{'、'.join(guidance.themes)}")
    if guidance.characters:
        lines.append(f"角色标签：{'、'.join(guidance.characters)}")
    if guidance.plots:
        lines.append(f"情节标签：{'、'.join(guidance.plots)}")
    if guidance.plot_brief:
        lines.append(f"剧情简述：{guidance.plot_brief}")

    if not lines:
        return ""
    rendered_lines = "\n".join(f"- {line}" for line in lines)
    return f"【灵感引导】\n{rendered_lines}"


def _merge_guidance_prompt(system_prompt: str, template: str, guidance_prompt: str) -> str:
    if not guidance_prompt or "{guidance_prompt}" in template:
        return system_prompt
    return f"{system_prompt}\n\n{guidance_prompt}"



class InspirationGenerateCardsResponse(BaseModel):
    """故事方向卡片生成响应契约。"""

    prompt: str | None = None
    cards: list[InspirationDirectionCard] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class InspirationMergeCardsRequest(BaseModel):
    """故事方向卡片合并请求契约。"""

    cards: list[InspirationDirectionCard] = Field(...)
    primary_card_id: str | None = None
    instructions: str | None = None


class InspirationMergeCardsResponse(BaseModel):
    """故事方向卡片合并响应契约。"""

    card: InspirationDirectionCard
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class InspirationStoryBibleDraft(BaseModel):
    """故事圣经草稿契约。"""

    core_idea: str
    story_promise: str
    target_genre: list[str]
    world_rules: list[str]
    core_conflict: str
    protagonist_profile: str
    antagonistic_force: str
    golden_finger: str | None = None
    opening_hook: str
    tone_and_style: str
    foreshadowing_seeds: list[str]
    constraints: list[str]

    @field_validator(
        "core_idea",
        "story_promise",
        "core_conflict",
        "protagonist_profile",
        "antagonistic_force",
        "opening_hook",
        "tone_and_style",
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("字段必须是非空字符串")
        return value.strip()

    @field_validator("target_genre", "world_rules", "foreshadowing_seeds", "constraints")
    @classmethod
    def _required_string_list(cls, value: list[str]) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ValueError("字段必须是非空字符串数组")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("数组项必须是非空字符串")
            normalized.append(item.strip())
        return normalized

    @field_validator("golden_finger")
    @classmethod
    def _optional_golden_finger(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("golden_finger必须是字符串、空字符串或null")
        return value.strip()


class InspirationGenerateStoryBibleRequest(BaseModel):
    """故事圣经草稿生成请求契约。"""

    idea: str | None = None
    direction_card: InspirationDirectionCard | None = None
    confirmed_fields: Dict[str, Any] = Field(default_factory=dict)
    user_edits: Dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


class InspirationGenerateStoryBibleResponse(BaseModel):
    """故事圣经草稿生成响应契约。"""

    story_bible_draft: InspirationStoryBibleDraft
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class InspirationQualityDimensions(BaseModel):
    """灵感质量评分维度。"""

    novelty: float = Field(..., ge=0, le=100)
    writability: float = Field(..., ge=0, le=100)
    commercial_hook: float = Field(..., ge=0, le=100)
    consistency: float = Field(..., ge=0, le=100)
    long_form_potential: float = Field(..., ge=0, le=100)

    @field_validator(
        "novelty",
        "writability",
        "commercial_hook",
        "consistency",
        "long_form_potential",
        mode="before",
    )
    @classmethod
    def _score_must_be_numeric(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("评分必须是0-100之间的数字")
        return value


class InspirationQualityIssue(BaseModel):
    """灵感质量问题项。"""

    id: str
    dimension: QualityDimension | None = None
    severity: Literal["info", "warning", "error"] | None = None
    message: str
    suggestion: str | None = None


class InspirationQualityReport(BaseModel):
    """灵感质量评估响应契约。"""

    overall_score: float = Field(..., ge=0, le=100)
    dimensions: InspirationQualityDimensions
    issues: list[InspirationQualityIssue] = Field(default_factory=list)
    repair_suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("overall_score", mode="before")
    @classmethod
    def _overall_score_must_be_numeric(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("overall_score必须是0-100之间的数字")
        return value


class InspirationEvaluateRequest(BaseModel):
    """灵感质量评估请求契约。"""

    direction_card: InspirationDirectionCard | None = None
    story_bible_draft: InspirationStoryBibleDraft | None = None
    context: Dict[str, Any] = Field(default_factory=dict)


class InspirationRepairRequest(BaseModel):
    """灵感草稿单次修复请求契约。"""

    draft: InspirationStoryBibleDraft | InspirationDirectionCard
    issues: list[InspirationQualityIssue] = Field(default_factory=list)
    issue_ids: list[str] = Field(default_factory=list)
    instructions: str | None = None


class InspirationRepairResult(BaseModel):
    """灵感草稿单次修复响应契约。"""

    repaired: bool
    draft: InspirationStoryBibleDraft | InspirationDirectionCard
    remaining_issues: list[InspirationQualityIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InspirationStructuredOutputError(ValueError):
    """结构化输出解析/验证失败，面向机器读取错误码。"""

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.code = INSPIRATION_STRUCTURED_OUTPUT_INVALID
        self.message = message
        self.details = details

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "error": self.code,
            "message": self.message,
        }
        if self.details is not None:
            payload["details"] = self.details
        return payload


def _validation_details(exc: ValidationError) -> list[dict[str, Any]]:
    """返回可JSON序列化的Pydantic错误详情。"""

    details: list[dict[str, Any]] = []
    for error in exc.errors():
        details.append(
            {
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return details


def parse_inspiration_structured_json(content: str) -> Any:
    """解析AI结构化JSON输出，失败时抛出机器可读错误码异常。"""

    if not isinstance(content, str) or not content.strip():
        raise InspirationStructuredOutputError("AI结构化输出为空")

    try:
        return loads_json(clean_json_response(content))
    except json.JSONDecodeError as exc:
        raise InspirationStructuredOutputError(
            "AI结构化输出不是合法JSON",
            details={"parse_error": str(exc)},
        ) from exc
    except Exception as exc:
        raise InspirationStructuredOutputError(
            "AI结构化输出解析失败",
            details={"parse_error": str(exc)},
        ) from exc


def _expect_mapping(value: Any, *, label: str = "AI结构化输出") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InspirationStructuredOutputError(f"{label}必须是JSON对象")
    return value


def _validate_model(model: type[TBaseModel], value: Any, *, label: str) -> TBaseModel:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise InspirationStructuredOutputError(
            f"{label}结构无效",
            details=_validation_details(exc),
        ) from exc


def _fresh_card_id(excluded_ids: set[str] | None = None) -> str:
    """生成不复用AI/source卡片ID的UUID字符串。"""

    excluded = excluded_ids or set()
    while True:
        card_id = str(uuid4())
        if card_id not in excluded:
            return card_id


def _normalize_card_similarity_text(value: str) -> str:
    """归一化方向卡标题/钩子，用于拦截重复或近似重复卡片。"""

    return "".join(char.lower() for char in value.strip() if char.isalnum())


def _is_card_text_too_similar(left: str, right: str) -> bool:
    left_key = _normalize_card_similarity_text(left)
    right_key = _normalize_card_similarity_text(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    shorter, longer = sorted((left_key, right_key), key=len)
    return len(shorter) >= 4 and shorter in longer


def _ensure_distinct_direction_cards(cards: list[InspirationDirectionCard]) -> None:
    """防止AI返回重复/近似重复的方向卡，避免用户看到无效比较项。"""

    for current_index, current_card in enumerate(cards):
        for previous_index, previous_card in enumerate(cards[:current_index]):
            if _is_card_text_too_similar(current_card.title, previous_card.title):
                raise InspirationStructuredOutputError(
                    "方向卡片存在重复或近似重复标题",
                    details={
                        "field": "title",
                        "first_index": previous_index,
                        "duplicate_index": current_index,
                    },
                )
            if _is_card_text_too_similar(current_card.hook, previous_card.hook):
                raise InspirationStructuredOutputError(
                    "方向卡片存在重复或近似重复钩子",
                    details={
                        "field": "hook",
                        "first_index": previous_index,
                        "duplicate_index": current_index,
                    },
                )


def _structured_output_http_error(exc: InspirationStructuredOutputError) -> HTTPException:
    """将结构化输出错误转换为受控4xx响应。"""

    return HTTPException(status_code=422, detail=exc.to_payload())


async def _collect_ai_text(
    ai_service: AIService,
    *,
    prompt: str,
    system_prompt: str,
    temperature: float,
) -> str:
    """收集现有AIService流式文本输出。"""

    accumulated_text = ""
    async for chunk in ai_service.generate_text_stream(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        auto_mcp=False,
        reasoning_intensity="auto",
    ):
        accumulated_text += chunk
    return accumulated_text


def _validate_generated_direction_cards_for_endpoint(
    content: str,
    *,
    expected_count: int,
) -> InspirationGenerateCardsResponse:
    """校验生成卡片输出，允许超量有效卡片截断但拒绝缺量/坏结构。"""

    payload = _expect_mapping(parse_inspiration_structured_json(content))
    try:
        response = InspirationGenerateCardsResponse.model_validate(payload)
    except ValidationError as exc:
        raise InspirationStructuredOutputError(
            "方向卡片结构无效",
            details=_validation_details(exc),
        ) from exc

    actual_count = len(response.cards)
    if actual_count < expected_count:
        raise InspirationStructuredOutputError(
            f"方向卡片数量不足，必须至少返回{expected_count}张有效卡片",
            details={"expected_count": expected_count, "actual_count": actual_count},
        )

    prompt = response.prompt.strip() if isinstance(response.prompt, str) else ""
    if not prompt:
        raise InspirationStructuredOutputError("方向卡片提示语缺失")

    warnings = list(response.warnings)
    cards = response.cards
    if actual_count > expected_count:
        warnings.append(f"AI返回{actual_count}张方向卡片，已截断为{expected_count}张。")
        cards = cards[:expected_count]

    _ensure_distinct_direction_cards(cards)

    excluded_ids = {card.id for card in response.cards}
    normalized_cards: list[InspirationDirectionCard] = []
    for card in cards:
        new_id = _fresh_card_id(excluded_ids)
        excluded_ids.add(new_id)
        normalized_cards.append(card.model_copy(update={"id": new_id}))

    return InspirationGenerateCardsResponse(
        prompt=prompt,
        cards=normalized_cards,
        warnings=warnings,
    )


def _validate_merged_direction_card_for_endpoint(
    content: str,
    *,
    source_card_ids: set[str],
) -> InspirationMergeCardsResponse:
    """校验合并卡片输出，并强制为合并结果分配新UUID。"""

    response = validate_inspiration_merged_card_output(content)
    excluded_ids = set(source_card_ids)
    excluded_ids.add(response.card.id)
    merged_card = response.card.model_copy(
        update={"id": _fresh_card_id(excluded_ids)}
    )
    return InspirationMergeCardsResponse(
        card=merged_card,
        warnings=response.warnings,
    )


def validate_inspiration_direction_cards_output(
    content: str | dict[str, Any],
    *,
    expected_count: int = 3,
) -> InspirationGenerateCardsResponse:
    """校验方向卡片输出；默认必须正好3张有效卡片。"""

    payload = _expect_mapping(
        parse_inspiration_structured_json(content) if isinstance(content, str) else content
    )
    try:
        response = InspirationGenerateCardsResponse.model_validate(payload)
    except ValidationError as exc:
        raise InspirationStructuredOutputError(
            "方向卡片结构无效",
            details=_validation_details(exc),
        ) from exc

    if len(response.cards) != expected_count:
        raise InspirationStructuredOutputError(
            f"方向卡片数量必须正好为{expected_count}张",
            details={"expected_count": expected_count, "actual_count": len(response.cards)},
        )
    _ensure_distinct_direction_cards(response.cards)
    return response


def validate_inspiration_merged_card_output(
    content: str | dict[str, Any],
) -> InspirationMergeCardsResponse:
    """校验方向卡片合并输出。"""

    payload = _expect_mapping(
        parse_inspiration_structured_json(content) if isinstance(content, str) else content
    )
    return _validate_model(
        InspirationMergeCardsResponse,
        payload,
        label="合并方向卡片",
    )


def validate_inspiration_story_bible_output(
    content: str | dict[str, Any],
) -> InspirationGenerateStoryBibleResponse:
    """校验故事圣经草稿输出。"""

    payload = _expect_mapping(
        parse_inspiration_structured_json(content) if isinstance(content, str) else content
    )
    return _validate_model(
        InspirationGenerateStoryBibleResponse,
        payload,
        label="故事圣经草稿",
    )


def validate_inspiration_quality_report_output(
    content: str | dict[str, Any],
) -> InspirationQualityReport:
    """校验质量报告输出，评分维度必须为0-100数字。"""

    payload = _expect_mapping(
        parse_inspiration_structured_json(content) if isinstance(content, str) else content
    )
    return _validate_model(
        InspirationQualityReport,
        payload,
        label="质量评估报告",
    )


def validate_inspiration_repair_result_output(
    content: str | dict[str, Any],
) -> InspirationRepairResult:
    """校验单次修复结果输出。"""

    payload = _expect_mapping(
        parse_inspiration_structured_json(content) if isinstance(content, str) else content
    )
    return _validate_model(
        InspirationRepairResult,
        payload,
        label="修复结果",
    )


def _inspiration_draft_kind(
    draft: InspirationStoryBibleDraft | InspirationDirectionCard,
) -> Literal["story_bible", "direction_card"]:
    """返回草稿类型，避免修复结果把故事圣经和方向卡片互换。"""

    if isinstance(draft, InspirationStoryBibleDraft):
        return "story_bible"
    return "direction_card"


def _requested_repair_issues(data: InspirationRepairRequest) -> list[InspirationQualityIssue]:
    """按用户显式选择过滤修复问题；未选择时默认传入全部问题。"""

    if not data.issue_ids:
        return list(data.issues)

    selected_ids = set(data.issue_ids)
    return [issue for issue in data.issues if issue.id in selected_ids]


def _repair_fallback_result(
    data: InspirationRepairRequest,
    warning: str,
    *,
    extra_warnings: list[str] | None = None,
) -> InspirationRepairResult:
    """修复失败时安全返回原稿，不让无效AI输出覆盖用户草稿。"""

    return InspirationRepairResult(
        repaired=False,
        draft=data.draft,
        remaining_issues=_requested_repair_issues(data),
        warnings=[warning, *(extra_warnings or [])],
    )


# 不同阶段的temperature设置（递减以保持一致性）
TEMPERATURE_SETTINGS = {
    "title": 0.8,        # 书名阶段可以更有创意
    "description": 0.65, # 简介需要贴合书名和原始想法
    "theme": 0.55,       # 主题需要更加贴合
    "genre": 0.45,       # 类型应该很明确
    # 新增步骤
    "world_setting": 0.7,
    "core_conflict": 0.6,
    "protagonist": 0.65,
    "golden_finger": 0.75,
    "auto": 0.7
}


def validate_options_response(result: Dict[str, Any], step: str, max_retries: int = 3) -> tuple[bool, str]:
    """
    校验AI返回的选项格式是否正确

    Returns:
        (is_valid, error_message)
    """
    # 检查必需字段
    if "options" not in result:
        return False, "缺少options字段"

    options = result.get("options", [])

    # 检查options是否为数组
    if not isinstance(options, list):
        return False, "options必须是数组"

    # 检查数组长度
    if len(options) < 3:
        return False, f"选项数量不足，至少需要3个，当前只有{len(options)}个"

    if len(options) > 10:
        return False, f"选项数量过多，最多10个，当前有{len(options)}个"

    # 检查每个选项是否为字符串且不为空
    for i, option in enumerate(options):
        if not isinstance(option, str):
            return False, f"第{i+1}个选项不是字符串类型"
        if not option.strip():
            return False, f"第{i+1}个选项为空"
        if len(option) > 500:
            return False, f"第{i+1}个选项过长（超过500字符）"

    # 根据不同步骤进行特定校验
    if step == "genre":
        # 类型标签应该比较短
        for i, option in enumerate(options):
            if len(option) > 10:
                return False, f"类型标签【{option}】过长，应该在2-10字之间"

    return True, ""


@router.post(
    "/generate-options",
    response_model=InspirationOptionsResponse,
    response_model_exclude_none=True,
)
async def generate_options(
    data: InspirationOptionsRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service)
) -> Dict[str, Any]:
    """
    根据当前收集的信息生成下一步的选项建议（带自动重试）

    Request:
        {
            "step": "title",  // title/description/theme/genre
            "context": {
                "title": "...",
                "description": "...",
                "theme": "..."
            }
        }

    Response:
        {
            "prompt": "引导语",
            "options": ["选项1", "选项2", ...]
        }
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            step = data.step
            context = data.context

            logger.info(f"灵感模式：生成{step}阶段的选项（第{attempt + 1}次尝试）")

            # 获取用户ID
            user_id: str = getattr(http_request.state, 'user_id', '') or ''

            # 获取对应的提示词模板（根据step确定模板key）
            # 新结构：每个步骤有独立的 SYSTEM 和 USER 模板
            template_key_map = {
                "title": ("INSPIRATION_TITLE_SYSTEM", "INSPIRATION_TITLE_USER"),
                "description": ("INSPIRATION_DESCRIPTION_SYSTEM", "INSPIRATION_DESCRIPTION_USER"),
                "theme": ("INSPIRATION_THEME_SYSTEM", "INSPIRATION_THEME_USER"),
                "genre": ("INSPIRATION_GENRE_SYSTEM", "INSPIRATION_GENRE_USER"),
                # 新增步骤
                "world_setting": ("INSPIRATION_WORLD_SYSTEM", "INSPIRATION_WORLD_USER"),
                "core_conflict": ("INSPIRATION_CONFLICT_SYSTEM", "INSPIRATION_CONFLICT_USER"),
                "protagonist": ("INSPIRATION_PROTAGONIST_SYSTEM", "INSPIRATION_PROTAGONIST_USER"),
                "golden_finger": ("INSPIRATION_GOLDEN_FINGER_SYSTEM", "INSPIRATION_GOLDEN_FINGER_USER"),
                "auto": ("INSPIRATION_DYNAMIC_SYSTEM", "INSPIRATION_DYNAMIC_USER")
            }
            template_keys = template_key_map.get(step)

            if not template_keys:
                return {
                    "error": f"不支持的步骤: {step}",
                    "prompt": "",
                    "options": []
                }

            system_key, user_key = template_keys

            # 获取自定义提示词模板（分别获取 system 和 user）
            system_template = await PromptService.get_template(system_key, user_id, db)
            user_template = await PromptService.get_template(user_key, user_id, db)

            # 准备格式化参数
            if step == "auto":
                format_params = {
                    "context_json": json.dumps(context, ensure_ascii=False, indent=2)
                }
            else:
                format_params = {
                    "initial_idea": context.get("initial_idea", context.get("description", "")),
                    "title": context.get("title", ""),
                    "description": context.get("description", ""),
                    "theme": context.get("theme", ""),
                    "genre": context.get("genre", ""),
                    "world_setting": context.get("world_setting", ""),
                    "core_conflict": context.get("core_conflict", ""),
                    "protagonist": context.get("protagonist", ""),
                    "golden_finger": context.get("golden_finger", "")
                }

            # 格式化提示词
            system_prompt = system_template.format(**format_params)
            user_prompt = user_template.format(**format_params)

            # 如果是重试，在提示词中强调格式要求
            if attempt > 0:
                system_prompt += f"\n\n⚠️ 这是第{attempt + 1}次生成，请务必严格按照JSON格式返回，确保options数组包含6个有效选项！"

            # 调用AI生成选项
            # 关键改进：使用递减的temperature以保持后续阶段与前文的一致性
            temperature = TEMPERATURE_SETTINGS.get(step, 0.7)
            logger.info(f"调用AI生成{step}选项... (temperature={temperature})")

            # 流式生成并累积文本
            accumulated_text = ""
            async for chunk in ai_service.generate_text_stream(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                auto_mcp=False,
                reasoning_intensity="auto",
            ):
                accumulated_text += chunk

            response = {"content": accumulated_text}
            content = accumulated_text
            logger.info(f"AI返回内容长度: {len(content)}")

            # 解析JSON（使用统一的JSON清洗方法）
            try:
                # 使用统一的JSON清洗方法
                cleaned_content = ai_service._clean_json_response(content)

                result = loads_json(cleaned_content)

                # 校验返回格式
                is_valid, error_msg = validate_options_response(result, step)

                if not is_valid:
                    logger.warning(f"⚠️ 第{attempt + 1}次生成格式校验失败: {error_msg}")
                    if attempt < max_retries - 1:
                        logger.info("准备重试...")
                        continue  # 重试
                    else:
                        # 最后一次尝试也失败了
                        return {
                            "prompt": f"请为【{step}】提供内容：",
                            "options": ["让AI重新生成", "我自己输入"],
                            "error": f"AI生成格式错误（{error_msg}），已自动重试{max_retries}次，请手动重试或自己输入"
                        }

                logger.info(f"✅ 第{attempt + 1}次成功生成{len(result.get('options', []))}个有效选项")
                return result

            except json.JSONDecodeError as e:
                logger.error(f"第{attempt + 1}次JSON解析失败: {e}")

                if attempt < max_retries - 1:
                    logger.info("JSON解析失败，准备重试...")
                    continue  # 重试
                else:
                    # 最后一次尝试也失败了
                    return {
                        "prompt": f"请为【{step}】提供内容：",
                        "options": ["让AI重新生成", "我自己输入"],
                        "error": f"AI返回格式错误，已自动重试{max_retries}次，请手动重试或自己输入"
                    }

        except Exception as e:
            logger.error(f"第{attempt + 1}次生成失败: {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.info("发生异常，准备重试...")
                continue
            else:
                return {
                    "error": str(e),
                    "prompt": "生成失败，请重试",
                    "options": ["重新生成", "我自己输入"]
                }

    # 理论上不会到这里
    return {
        "error": "生成失败",
        "prompt": "请重试",
        "options": []
    }


@router.post(
    "/refine-options",
    response_model=InspirationOptionsResponse,
    response_model_exclude_none=True,
)
async def refine_options(
    data: InspirationRefineOptionsRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service)
) -> Dict[str, Any]:
    """
    基于用户反馈重新生成选项（支持多轮对话）

    Request:
        {
            "step": "title",  // 当前步骤
            "context": {
                "initial_idea": "...",
                "title": "...",
                "description": "...",
                "theme": "..."
            },
            "feedback": "我想要更悲剧一些的主题",  // 用户反馈
            "previous_options": ["选项1", "选项2", ...]  // 之前的选项（可选）
        }

    Response:
        {
            "prompt": "引导语",
            "options": ["新选项1", "新选项2", ...]
        }
    """
    max_retries = 3

    for attempt in range(max_retries):
        try:
            step = data.step
            context = data.context
            feedback = data.feedback
            previous_options = data.previous_options

            logger.info(f"灵感模式：根据反馈重新生成{step}阶段的选项（第{attempt + 1}次尝试）")
            logger.info(f"用户反馈: {feedback}")

            # 获取用户ID
            user_id: str = getattr(http_request.state, 'user_id', '') or ''

            # 获取对应的提示词模板
            template_key_map = {
                "title": ("INSPIRATION_TITLE_SYSTEM", "INSPIRATION_TITLE_USER"),
                "description": ("INSPIRATION_DESCRIPTION_SYSTEM", "INSPIRATION_DESCRIPTION_USER"),
                "theme": ("INSPIRATION_THEME_SYSTEM", "INSPIRATION_THEME_USER"),
                "genre": ("INSPIRATION_GENRE_SYSTEM", "INSPIRATION_GENRE_USER"),
                # 新增步骤
                "world_setting": ("INSPIRATION_WORLD_SYSTEM", "INSPIRATION_WORLD_USER"),
                "core_conflict": ("INSPIRATION_CONFLICT_SYSTEM", "INSPIRATION_CONFLICT_USER"),
                "protagonist": ("INSPIRATION_PROTAGONIST_SYSTEM", "INSPIRATION_PROTAGONIST_USER"),
                "golden_finger": ("INSPIRATION_GOLDEN_FINGER_SYSTEM", "INSPIRATION_GOLDEN_FINGER_USER"),
                "auto": ("INSPIRATION_DYNAMIC_SYSTEM", "INSPIRATION_DYNAMIC_USER")
            }
            template_keys = template_key_map.get(step)

            if not template_keys:
                return {
                    "error": f"不支持的步骤: {step}",
                    "prompt": "",
                    "options": []
                }

            system_key, user_key = template_keys

            # 获取自定义提示词模板
            system_template = await PromptService.get_template(system_key, user_id, db)
            user_template = await PromptService.get_template(user_key, user_id, db)

            # 准备格式化参数
            if step == "auto":
                format_params = {
                    "context_json": json.dumps(context, ensure_ascii=False, indent=2)
                }
            else:
                format_params = {
                    "initial_idea": context.get("initial_idea", context.get("description", "")),
                    "title": context.get("title", ""),
                    "description": context.get("description", ""),
                    "theme": context.get("theme", ""),
                    "genre": context.get("genre", ""),
                    "world_setting": context.get("world_setting", ""),
                    "core_conflict": context.get("core_conflict", ""),
                    "protagonist": context.get("protagonist", ""),
                    "golden_finger": context.get("golden_finger", "")
                }

            # 格式化提示词
            system_prompt = system_template.format(**format_params)
            user_prompt = user_template.format(**format_params)

            # 添加反馈信息到提示词
            feedback_instruction = f"""

⚠️ 用户对之前的选项不太满意，提供了以下反馈：
「{feedback}」

之前生成的选项：
{chr(10).join([f"- {opt}" for opt in previous_options]) if previous_options else "（无）"}

请根据用户的反馈调整生成策略，提供更符合用户期望的新选项。
注意：
1. 仔细理解用户的反馈意图
2. 生成的新选项要明显体现用户要求的调整方向
3. 保持与已有上下文的一致性
4. 确保返回6个有效选项
"""

            system_prompt += feedback_instruction

            # 如果是重试，强调格式要求
            if attempt > 0:
                system_prompt += f"\n\n⚠️ 这是第{attempt + 1}次生成，请务必严格按照JSON格式返回！"

            # 调用AI生成选项
            temperature = TEMPERATURE_SETTINGS.get(step, 0.7)
            # 反馈生成时使用稍高的temperature以获得更多样化的结果
            temperature = min(temperature + 0.1, 0.9)
            logger.info(f"调用AI根据反馈生成{step}选项... (temperature={temperature})")

            # 流式生成并累积文本
            accumulated_text = ""
            async for chunk in ai_service.generate_text_stream(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                auto_mcp=False,
                reasoning_intensity="auto",
            ):
                accumulated_text += chunk

            content = accumulated_text
            logger.info(f"AI返回内容长度: {len(content)}")

            # 解析JSON
            try:
                cleaned_content = ai_service._clean_json_response(content)
                result = loads_json(cleaned_content)

                # 校验返回格式
                is_valid, error_msg = validate_options_response(result, step)

                if not is_valid:
                    logger.warning(f"⚠️ 第{attempt + 1}次生成格式校验失败: {error_msg}")
                    if attempt < max_retries - 1:
                        logger.info("准备重试...")
                        continue
                    else:
                        return {
                            "prompt": f"请为【{step}】提供内容：",
                            "options": ["让AI重新生成", "我自己输入"],
                            "error": f"AI生成格式错误（{error_msg}），已自动重试{max_retries}次"
                        }

                logger.info(f"✅ 第{attempt + 1}次根据反馈成功生成{len(result.get('options', []))}个有效选项")
                return result

            except json.JSONDecodeError as e:
                logger.error(f"第{attempt + 1}次JSON解析失败: {e}")

                if attempt < max_retries - 1:
                    logger.info("JSON解析失败，准备重试...")
                    continue
                else:
                    return {
                        "prompt": f"请为【{step}】提供内容：",
                        "options": ["让AI重新生成", "我自己输入"],
                        "error": f"AI返回格式错误，已自动重试{max_retries}次"
                    }

        except Exception as e:
            logger.error(f"第{attempt + 1}次根据反馈生成失败: {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.info("发生异常，准备重试...")
                continue
            else:
                return {
                    "error": str(e),
                    "prompt": "生成失败，请重试",
                    "options": ["重新生成", "我自己输入"]
                }

    return {
        "error": "生成失败",
        "prompt": "请重试",
        "options": []
    }


@router.post(
    "/generate-cards",
    response_model=InspirationGenerateCardsResponse,
    response_model_exclude_none=True,
)
async def generate_cards(
    data: InspirationGenerateCardsRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service),
) -> InspirationGenerateCardsResponse:
    """根据一个灵感创意生成可比较的故事方向卡片。"""

    try:
        user_id: str = getattr(http_request.state, 'user_id', '') or ''
        template = await PromptService.get_template(
            "INSPIRATION_DIRECTION_CARDS",
            user_id,
            db,
        )
        guidance_prompt = build_inspiration_guidance_prompt(data.guidance)
        system_prompt = PromptService.format_prompt(
            template,
            idea=data.idea or "",
            context_json=json.dumps(data.context, ensure_ascii=False, indent=2),
            card_count=data.card_count,
            guidance_prompt=guidance_prompt,
        )
        system_prompt = _merge_guidance_prompt(system_prompt, template, guidance_prompt)
        user_prompt = "请基于上述创意和上下文生成故事方向卡片。"

        logger.info("灵感模式：生成方向卡片 card_count=%s", data.card_count)
        content = await _collect_ai_text(
            ai_service,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
        )
        return _validate_generated_direction_cards_for_endpoint(
            content,
            expected_count=data.card_count,
        )
    except InspirationStructuredOutputError as exc:
        logger.warning("方向卡片结构化输出无效: %s", exc.message)
        raise _structured_output_http_error(exc) from exc


@router.post(
    "/merge-cards",
    response_model=InspirationMergeCardsResponse,
    response_model_exclude_none=True,
)
async def merge_cards(
    data: InspirationMergeCardsRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service),
) -> InspirationMergeCardsResponse:
    """合并两张方向卡片为一张新的故事方向卡片。"""

    if len(data.cards) != 2:
        raise HTTPException(
            status_code=400,
            detail={
                "code": INSPIRATION_STRUCTURED_OUTPUT_INVALID,
                "error": INSPIRATION_STRUCTURED_OUTPUT_INVALID,
                "message": "方向卡片合并必须且只能提供两张卡片",
                "details": {"expected_count": 2, "actual_count": len(data.cards)},
            },
        )

    try:
        user_id: str = getattr(http_request.state, 'user_id', '') or ''
        template = await PromptService.get_template(
            "INSPIRATION_MERGE_CARDS",
            user_id,
            db,
        )
        cards_json = json.dumps(
            [card.model_dump() for card in data.cards],
            ensure_ascii=False,
            indent=2,
        )
        system_prompt = PromptService.format_prompt(
            template,
            cards_json=cards_json,
            primary_card_id=data.primary_card_id or data.cards[0].id,
            instructions=data.instructions or "",
        )
        user_prompt = "请合并这两张故事方向卡片，并只返回合并后的JSON结果。"

        logger.info("灵感模式：合并方向卡片")
        content = await _collect_ai_text(
            ai_service,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.6,
        )
        return _validate_merged_direction_card_for_endpoint(
            content,
            source_card_ids={card.id for card in data.cards},
        )
    except InspirationStructuredOutputError as exc:
        logger.warning("合并方向卡片结构化输出无效: %s", exc.message)
        raise _structured_output_http_error(exc) from exc


@router.post(
    "/generate-story-bible",
    response_model=InspirationGenerateStoryBibleResponse,
    response_model_exclude={"error"},
)
async def generate_story_bible(
    data: InspirationGenerateStoryBibleRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service),
) -> InspirationGenerateStoryBibleResponse:
    """根据原始创意、方向卡和已确认字段生成本地草稿用故事圣经。"""

    try:
        user_id: str = getattr(http_request.state, 'user_id', '') or ''
        template = await PromptService.get_template(
            "INSPIRATION_STORY_BIBLE",
            user_id,
            db,
        )
        direction_card_payload = data.direction_card.model_dump() if data.direction_card else None
        system_prompt = PromptService.format_prompt(
            template,
            idea=(data.idea or "").strip(),
            direction_card_json=json.dumps(direction_card_payload, ensure_ascii=False, indent=2),
            confirmed_fields_json=json.dumps(data.confirmed_fields, ensure_ascii=False, indent=2),
            user_edits_json=json.dumps(data.user_edits, ensure_ascii=False, indent=2),
            constraints_json=json.dumps(data.constraints, ensure_ascii=False, indent=2),
        )
        user_prompt = "请基于上述素材生成故事圣经草稿，并只返回JSON结果。"

        logger.info("灵感模式：生成故事圣经草稿")
        content = await _collect_ai_text(
            ai_service,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.55,
        )
        return validate_inspiration_story_bible_output(content)
    except InspirationStructuredOutputError as exc:
        logger.warning("故事圣经草稿结构化输出无效: %s", exc.message)
        raise _structured_output_http_error(exc) from exc


@router.post(
    "/evaluate",
    response_model=InspirationQualityReport,
    response_model_exclude_none=True,
)
async def evaluate_inspiration(
    data: InspirationEvaluateRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service),
) -> InspirationQualityReport:
    """对方向卡或故事圣经草稿做结构化质量评估。"""

    draft = data.story_bible_draft or data.direction_card
    if draft is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": INSPIRATION_STRUCTURED_OUTPUT_INVALID,
                "error": INSPIRATION_STRUCTURED_OUTPUT_INVALID,
                "message": "质量评估需要提供方向卡片或故事圣经草稿",
            },
        )

    try:
        user_id: str = getattr(http_request.state, 'user_id', '') or ''
        template = await PromptService.get_template(
            "INSPIRATION_QUALITY_CHECK",
            user_id,
            db,
        )
        system_prompt = PromptService.format_prompt(
            template,
            draft_json=json.dumps(draft.model_dump(), ensure_ascii=False, indent=2),
            context_json=json.dumps(data.context, ensure_ascii=False, indent=2),
        )
        user_prompt = "请评估上述灵感草稿质量，并只返回JSON结果。"

        logger.info("灵感模式：评估灵感质量")
        content = await _collect_ai_text(
            ai_service,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.35,
        )
        return validate_inspiration_quality_report_output(content)
    except InspirationStructuredOutputError as exc:
        logger.warning("灵感质量评估结构化输出无效: %s", exc.message)
        raise _structured_output_http_error(exc) from exc


@router.post(
    "/repair",
    response_model=InspirationRepairResult,
)
async def repair_inspiration(
    data: InspirationRepairRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service),
) -> InspirationRepairResult:
    """对方向卡或故事圣经草稿做一次且仅一次定向修复。"""

    original_kind = _inspiration_draft_kind(data.draft)
    repair_issues = _requested_repair_issues(data)
    issue_payload = {
        "selected_issue_ids": data.issue_ids,
        "issues": [issue.model_dump(exclude_none=True) for issue in repair_issues],
    }

    try:
        user_id: str = getattr(http_request.state, 'user_id', '') or ''
        template = await PromptService.get_template(
            "INSPIRATION_REPAIR",
            user_id,
            db,
        )
        system_prompt = PromptService.format_prompt(
            template,
            draft_json=json.dumps(data.draft.model_dump(), ensure_ascii=False, indent=2),
            issues_json=json.dumps(issue_payload, ensure_ascii=False, indent=2),
            instructions=(data.instructions or "请只做一次针对性修复，保留原有核心前提和未涉及字段。").strip(),
        )
        user_prompt = "请对上述灵感草稿执行一次定向修复，并只返回JSON结果。"

        logger.info("灵感模式：单次修复灵感草稿")
        content = await _collect_ai_text(
            ai_service,
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.45,
        )
        result = validate_inspiration_repair_result_output(content)
    except InspirationStructuredOutputError as exc:
        logger.warning("灵感修复结构化输出无效，保留原稿: %s", exc.message)
        return _repair_fallback_result(
            data,
            "修复输出结构无效，已保留原始草稿。",
            extra_warnings=[exc.message],
        )

    if _inspiration_draft_kind(result.draft) != original_kind:
        logger.warning("灵感修复输出类型与原始草稿不一致，保留原稿")
        return _repair_fallback_result(
            data,
            "修复输出类型与原始草稿不一致，已保留原始草稿。",
            extra_warnings=result.warnings,
        )

    if not result.repaired:
        return InspirationRepairResult(
            repaired=False,
            draft=data.draft,
            remaining_issues=result.remaining_issues or repair_issues,
            warnings=result.warnings or ["本次修复未能完成，已保留原始草稿。"],
        )

    return result


@router.post(
    "/quick-generate",
    response_model=InspirationQuickGenerateResponse,
    response_model_exclude_none=True,
)
async def quick_generate(
    data: InspirationQuickGenerateRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
    ai_service: AIService = Depends(get_user_ai_service)
) -> Dict[str, Any]:
    """
    智能补全：根据用户已提供的部分信息，AI自动补全缺失字段

    Request:
        {
            "title": "书名（可选）",
            "description": "简介（可选）",
            "theme": "主题（可选）",
            "genre": ["类型1", "类型2"]（可选）
        }

    Response:
        {
            "title": "补全的书名",
            "description": "补全的简介",
            "theme": "补全的主题",
            "genre": ["补全的类型"]
        }
    """
    try:
        payload = data.model_dump(exclude_none=True)
        logger.info("灵感模式：智能补全")

        # 获取用户ID
        user_id: str = getattr(http_request.state, 'user_id', '') or ''

        # 构建补全提示词
        existing_info = []
        if payload.get("title"):
            existing_info.append(f"- 书名：{payload['title']}")
        if payload.get("description"):
            existing_info.append(f"- 简介：{payload['description']}")
        if payload.get("theme"):
            existing_info.append(f"- 主题：{payload['theme']}")
        if payload.get("genre"):
            genre_value = payload["genre"]
            genre_list = genre_value if isinstance(genre_value, list) else [genre_value]
            existing_info.append(f"- 类型：{', '.join(genre_list)}")

        existing_text = "\n".join(existing_info) if existing_info else "暂无信息"

        # 获取自定义提示词模板
        system_template = await PromptService.get_template("INSPIRATION_QUICK_COMPLETE", user_id, db)

        # 格式化提示词
        prompts = {
            "system": PromptService.format_prompt(system_template, existing=existing_text),
            "user": "请补全小说信息"
        }

        # 调用AI - 流式生成并累积文本
        accumulated_text = ""
        async for chunk in ai_service.generate_text_stream(
            prompt=prompts["user"],
            system_prompt=prompts["system"],
            temperature=0.7,
            auto_mcp=False,
            reasoning_intensity="auto",
        ):
            accumulated_text += chunk

        response = {"content": accumulated_text}
        content = accumulated_text

        # 解析JSON（使用统一的JSON清洗方法）
        try:
            # 使用统一的JSON清洗方法
            cleaned_content = ai_service._clean_json_response(content)

            result = loads_json(cleaned_content)

            # 合并用户已提供的信息（用户输入优先）
            supplied_genre = payload.get("genre")
            supplied_genre_list = supplied_genre if isinstance(supplied_genre, list) else ([supplied_genre] if supplied_genre else None)
            generated_genre = result.get("genre", [])
            generated_genre_list = generated_genre if isinstance(generated_genre, list) else ([generated_genre] if generated_genre else [])
            final_result = {
                "title": payload.get("title") or result.get("title", ""),
                "description": payload.get("description") or result.get("description", ""),
                "theme": payload.get("theme") or result.get("theme", ""),
                "genre": supplied_genre_list or generated_genre_list
            }

            logger.info(f"✅ 智能补全成功")
            return final_result

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            raise Exception("AI返回格式错误，请重试")

    except Exception as e:
        logger.error(f"智能补全失败: {e}", exc_info=True)
        return {
            "error": str(e)
        }
