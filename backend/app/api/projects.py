"""项目管理API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from collections.abc import AsyncGenerator, Mapping
from typing import cast
import json
from urllib.parse import quote
from app.database import get_db
from app.models.project import Project
from app.models.character import Character
from app.models.outline import Outline
from app.models.chapter import Chapter
from app.models.generation_history import GenerationHistory
from app.models.relationship import EntityRelationship, Organization, OrganizationMember
from app.models.memory import StoryMemory
from app.models.foreshadow import Foreshadow
from app.models.career import Career, CharacterCareer
from app.models.analysis_task import AnalysisTask
from app.models.batch_generation_task import BatchGenerationTask
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse
)
from app.schemas.import_export import (
    ExportOptions,
    ImportValidationResult,
    ImportResult
)
from app.services.import_export_service import ImportExportService
from app.services.memory_service import memory_service
from app.logger import get_logger
from app.utils.data_consistency import (
    run_full_data_consistency_check,
    fix_missing_organization_records,
    fix_organization_member_counts
)
from app.api.common import verify_project_access
from app.api.settings import get_user_ai_service_from_db
from app.schemas.project_optimize import (
    FieldSuggestion,
    ProjectOptimizeRequest,
    ProjectOptimizeResult,
    filter_and_validate_suggestions,
)
from app.services.ai_service import AIService
from app.services.json_helper import loads_json
from app.services.prompt_service import PromptService
from app.utils.sse_response import SSEResponse, create_sse_response

logger = get_logger(__name__)
router = APIRouter(prefix="/projects", tags=["项目管理"])


PROJECT_OPTIMIZE_CONTEXT_LIMIT = 10
PROJECT_OPTIMIZE_OUTLINE_TEXT_LIMIT = 100
PROJECT_OPTIMIZE_CHARACTER_TEXT_LIMIT = 50


def _truncate_for_optimize_prompt(value: object, max_length: int) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "…"


def _json_for_optimize_prompt(value: object) -> str:
    if value in (None, [], {}):
        return "无"
    return json.dumps(value, ensure_ascii=False, default=str)


def _project_optimize_field_value(project: Project, field_name: str) -> str:
    return "" if getattr(project, field_name, None) is None else str(getattr(project, field_name))


async def _build_project_optimize_context(project_id: str, db: AsyncSession) -> tuple[str, str]:
    outlines_result = await db.execute(
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.order_index)
        .limit(PROJECT_OPTIMIZE_CONTEXT_LIMIT)
    )
    outlines = outlines_result.scalars().all()
    if outlines:
        outline_lines = []
        for index, outline in enumerate(outlines, start=1):
            summary_source = outline.content or outline.structure or ""
            summary = _truncate_for_optimize_prompt(summary_source, PROJECT_OPTIMIZE_OUTLINE_TEXT_LIMIT)
            title = _truncate_for_optimize_prompt(outline.title, 40) or f"大纲{index}"
            outline_lines.append(f"{index}. {title}: {summary or '暂无摘要'}")
        outline_summary = "\n".join(outline_lines)
    else:
        outline_summary = "暂无大纲"

    characters_result = await db.execute(
        select(Character)
        .where(Character.project_id == project_id)
        .order_by(Character.created_at, Character.id)
        .limit(PROJECT_OPTIMIZE_CONTEXT_LIMIT)
    )
    characters = characters_result.scalars().all()
    if characters:
        character_lines = []
        for index, character in enumerate(characters, start=1):
            parts = [
                character.role_type,
                character.personality,
                character.background,
                character.motivations,
                character.arc_summary,
                character.current_state,
            ]
            summary_source = "；".join(str(part).strip() for part in parts if part)
            summary = _truncate_for_optimize_prompt(summary_source, PROJECT_OPTIMIZE_CHARACTER_TEXT_LIMIT)
            name = _truncate_for_optimize_prompt(character.name, 30) or f"角色{index}"
            character_lines.append(f"{index}. {name}: {summary or '暂无摘要'}")
        character_summary = "\n".join(character_lines)
    else:
        character_summary = "暂无角色"

    return outline_summary, character_summary


def _parse_project_optimize_ai_response(ai_response: object) -> dict[str, object]:
    if isinstance(ai_response, str):
        response_text = ai_response
    else:
        response_text = json.dumps(ai_response, ensure_ascii=False, default=str)

    cleaned_response = AIService._clean_json_response(response_text)
    parsed = loads_json(cleaned_response)
    if not isinstance(parsed, dict):
        raise ValueError("项目优化AI响应必须是JSON对象")
    return cast(dict[str, object], parsed)


def _build_project_optimize_result(parsed_response: Mapping[str, object]) -> ProjectOptimizeResult:
    raw_fields = parsed_response.get("fields")
    if not isinstance(raw_fields, Mapping):
        raw_fields = {}

    raw_values: dict[str, object] = {}
    raw_reasons: dict[str, str] = {}
    for field_name, suggestion in raw_fields.items():
        if isinstance(suggestion, Mapping):
            raw_values[str(field_name)] = suggestion.get("value")
            reason = suggestion.get("reason")
            raw_reasons[str(field_name)] = "" if reason is None else str(reason)
        else:
            raw_values[str(field_name)] = suggestion
            raw_reasons[str(field_name)] = ""

    filtered_values = filter_and_validate_suggestions(raw_values)
    fields = {
        field_name: FieldSuggestion(
            value=value,
            reason=raw_reasons.get(field_name) or "基于项目设定、大纲与角色上下文的优化建议。",
        )
        for field_name, value in filtered_values.items()
    }

    reply = parsed_response.get("reply")
    reply_text = str(reply).strip() if reply is not None else ""
    if not reply_text:
        reply_text = "已完成项目设定分析，请查看字段优化建议。" if fields else "当前项目设定已较一致，暂时不需要调整项目字段。"

    return ProjectOptimizeResult(fields=fields, reply=reply_text)


async def _project_optimize_generator(
    project_id: str,
    project: Project,
    data: ProjectOptimizeRequest,
    user_id: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    try:
        yield await SSEResponse.send_progress("正在分析项目设定…", 10, "processing")

        outline_summary, character_summary = await _build_project_optimize_context(project_id, db)

        yield await SSEResponse.send_progress("正在整理大纲与角色摘要…", 35, "processing")

        template = await PromptService.get_template("PROJECT_OPTIMIZE", user_id, db)
        prompt = PromptService.format_prompt(
            template,
            title=_project_optimize_field_value(project, "title"),
            description=_project_optimize_field_value(project, "description"),
            theme=_project_optimize_field_value(project, "theme"),
            genre=_project_optimize_field_value(project, "genre"),
            world_time_period=_project_optimize_field_value(project, "world_time_period"),
            world_location=_project_optimize_field_value(project, "world_location"),
            world_atmosphere=_project_optimize_field_value(project, "world_atmosphere"),
            world_rules=_project_optimize_field_value(project, "world_rules"),
            narrative_perspective=_project_optimize_field_value(project, "narrative_perspective"),
            outline_summary=outline_summary,
            character_summary=character_summary,
            requirement=data.requirement or "",
            conversation_history=_json_for_optimize_prompt(data.conversation_history),
            current_draft=_json_for_optimize_prompt(data.current_draft),
        )

        yield await SSEResponse.send_progress("正在生成优化建议…", 60, "processing")

        user_ai_service = await get_user_ai_service_from_db(user_id, db)
        ai_response = await user_ai_service.call_with_json_retry(
            prompt=prompt,
            expected_type="object",
            auto_mcp=False,
        )

        yield await SSEResponse.send_progress("正在校验优化建议…", 85, "processing")

        parsed_response = _parse_project_optimize_ai_response(ai_response)
        result = _build_project_optimize_result(parsed_response)

        yield await SSEResponse.send_result(result.model_dump())
        yield await SSEResponse.send_done()
    except Exception as e:
        logger.error(f"项目设定优化失败: project_id={project_id}, error={str(e)}", exc_info=True)
        yield await SSEResponse.send_error(str(e), 500)


@router.post("", response_model=ProjectResponse, summary="创建项目")
async def create_project(
    project: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试创建项目")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"创建新项目: {project.title}, user_id={user_id}")
        
        # 创建项目时自动设置user_id
        project_data = project.model_dump()
        project_data['user_id'] = user_id
        db_project = Project(**project_data)
        
        db.add(db_project)
        await db.commit()
        await db.refresh(db_project)
        logger.info(f"项目创建成功: project_id={db_project.id}, user_id={user_id}")
        
        return db_project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建项目失败: {str(e)}", exc_info=True)
        raise


@router.get("", response_model=ProjectListResponse, summary="获取项目列表")
async def get_projects(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """获取当前用户的项目列表"""
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试获取项目列表")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.debug(f"获取项目列表: user_id={user_id}, skip={skip}, limit={limit}")
        
        # 只查询当前用户的项目
        count_result = await db.execute(
            select(func.count(Project.id)).where(Project.user_id == user_id)
        )
        total = count_result.scalar_one()
        
        result = await db.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        projects = result.scalars().all()
        logger.info(f"获取项目列表成功: user_id={user_id}, 共{total}个项目")
        
        return ProjectListResponse(total=total, items=projects)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目列表失败: {str(e)}", exc_info=True)
        raise


@router.get("/{project_id}", response_model=ProjectResponse, summary="获取项目详情")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试获取项目详情")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.debug(f"获取项目详情: project_id={project_id}, user_id={user_id}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        logger.info(f"获取项目详情成功: {project.title}")
        return project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目详情失败: {str(e)}", exc_info=True)
        raise


@router.post("/{project_id}/optimize-stream", summary="AI优化项目设定(SSE)")
async def optimize_project_stream(
    project_id: str,
    data: ProjectOptimizeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", None)
    project = await verify_project_access(project_id, user_id, db)

    return create_sse_response(
        _project_optimize_generator(
            project_id=project_id,
            project=project,
            data=data,
            user_id=str(user_id),
            db=db,
        )
    )


@router.put("/{project_id}", response_model=ProjectResponse, summary="更新项目")
async def update_project(
    project_id: str,
    project_update: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试更新项目")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"更新项目: project_id={project_id}, user_id={user_id}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        update_data = project_update.model_dump(exclude_unset=True)
        logger.debug(f"更新字段: {list(update_data.keys())}")
        for field, value in update_data.items():
            setattr(project, field, value)
        
        await db.commit()
        await db.refresh(project)
        logger.info(f"项目更新成功: {project.title}")
        return project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新项目失败: {str(e)}", exc_info=True)
        raise


@router.delete("/{project_id}", summary="删除项目")
async def delete_project(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试删除项目")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"删除项目: project_id={project_id}, user_id={user_id}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        project_title = project.title
        
        # 删除向量数据库中的记忆（user_id已在上面获取）
        if user_id:
            try:
                await memory_service.delete_project_memories(user_id, project_id)
                logger.info(f"✅ 向量数据库清理成功")
            except Exception as e:
                logger.warning(f"⚠️ 向量数据库清理失败（继续删除其他数据）: {str(e)}")
        else:
            logger.warning(f"⚠️ 未找到用户ID，跳过向量数据库清理")
        
        # === 删除所有关联数据（SQLite默认不启用外键约束，需要显式删除）===
        
        # 1. 删除角色关系
        relationships_result = await db.execute(
            delete(EntityRelationship).where(EntityRelationship.project_id == project_id)
        )
        logger.debug(f"删除角色关系数: {relationships_result.rowcount}")
        
        # 2. 删除组织成员和组织
        orgs_result = await db.execute(
            select(Organization).where(Organization.project_id == project_id)
        )
        orgs = orgs_result.scalars().all()
        org_member_count = 0
        for org in orgs:
            members_result = await db.execute(
                delete(OrganizationMember).where(OrganizationMember.organization_id == org.id)
            )
            org_member_count += members_result.rowcount
        logger.debug(f"删除组织成员数: {org_member_count}")
        
        organizations_result = await db.execute(
            delete(Organization).where(Organization.project_id == project_id)
        )
        logger.debug(f"删除组织数: {organizations_result.rowcount}")
        
        # 3. 删除生成历史
        history_result = await db.execute(
            delete(GenerationHistory).where(GenerationHistory.project_id == project_id)
        )
        logger.debug(f"删除生成历史数: {history_result.rowcount}")
        
        # 4. 删除分析任务
        analysis_tasks_result = await db.execute(
            delete(AnalysisTask).where(AnalysisTask.project_id == project_id)
        )
        logger.debug(f"删除分析任务数: {analysis_tasks_result.rowcount}")
        
        # 5. 删除批量生成任务
        batch_tasks_result = await db.execute(
            delete(BatchGenerationTask).where(BatchGenerationTask.project_id == project_id)
        )
        logger.debug(f"删除批量生成任务数: {batch_tasks_result.rowcount}")
        
        # 6. 删除角色职业关联（先获取角色ID列表）
        characters_query = await db.execute(
            select(Character.id).where(Character.project_id == project_id)
        )
        character_ids = [row[0] for row in characters_query.fetchall()]
        
        if character_ids:
            character_careers_result = await db.execute(
                delete(CharacterCareer).where(CharacterCareer.character_id.in_(character_ids))
            )
            logger.debug(f"删除角色职业关联数: {character_careers_result.rowcount}")
        
        # 7. 删除职业体系
        careers_result = await db.execute(
            delete(Career).where(Career.project_id == project_id)
        )
        logger.debug(f"删除职业体系数: {careers_result.rowcount}")
        
        # 8. 删除故事记忆
        story_memories_result = await db.execute(
            delete(StoryMemory).where(StoryMemory.project_id == project_id)
        )
        logger.debug(f"删除故事记忆数: {story_memories_result.rowcount}")
        
        # 9. 删除章节（会级联删除 PlotAnalysis）
        chapters_result = await db.execute(
            delete(Chapter).where(Chapter.project_id == project_id)
        )
        logger.debug(f"删除章节数: {chapters_result.rowcount}")
        
        # 10. 删除大纲
        outlines_result = await db.execute(
            delete(Outline).where(Outline.project_id == project_id)
        )
        logger.debug(f"删除大纲数: {outlines_result.rowcount}")
        
        # 11. 删除角色
        characters_result = await db.execute(
            delete(Character).where(Character.project_id == project_id)
        )
        logger.debug(f"删除角色数: {characters_result.rowcount}")
        
        # 12. 删除伏笔
        foreshadows_result = await db.execute(
            delete(Foreshadow).where(Foreshadow.project_id == project_id)
        )
        logger.debug(f"删除伏笔数: {foreshadows_result.rowcount}")
        
        # 最后删除项目本身
        await db.delete(project)
        await db.commit()
        
        logger.info(f"项目删除成功: {project_title}")
        return {"message": "项目及所有关联数据（包括向量数据库）删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除项目失败: {str(e)}", exc_info=True)
        raise


@router.get("/{project_id}/export", summary="导出项目章节为TXT")
async def export_project_chapters(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """
    导出项目的所有章节内容为TXT文本文件
    按章节顺序组织，使用便于再次拆书导入的纯章节格式
    """
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试导出项目")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"开始导出项目: project_id={project_id}, user_id={user_id}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        chapters_result = await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.chapter_number)
        )
        chapters = chapters_result.scalars().all()
        
        if not chapters:
            logger.warning(f"项目没有章节: {project_id}")
            raise HTTPException(status_code=404, detail="项目没有任何章节")
        
        txt_content = []
        
        for idx, chapter in enumerate(chapters):
            chapter_title = (chapter.title or "").strip() or f"未命名章节{chapter.chapter_number}"
            raw_content = (chapter.content or "").strip()
            if raw_content:
                formatted_lines = []
                for line in raw_content.splitlines():
                    stripped_line = line.strip()
                    if stripped_line:
                        formatted_lines.append(f"　　{stripped_line}")
                    else:
                        formatted_lines.append("")
                chapter_content = "\n".join(formatted_lines)
            else:
                chapter_content = "　　（本章暂无内容）"
            
            # 使用拆书强匹配可稳定识别的章节标题格式：第X章 标题
            txt_content.append(f"第{chapter.chapter_number}章 {chapter_title}")
            txt_content.append(chapter_content)
            
            # 章节之间只保留一个空行，避免装饰性分割线干扰拆书识别
            if idx < len(chapters) - 1:
                txt_content.append("")
        
        final_content = "\n".join(txt_content)
        
        safe_title = "".join(c for c in (project.title or "未命名项目") if c.isalnum() or c in (' ', '-', '_', '，', '。', '、'))
        filename = f"{safe_title}.txt"
        
        from urllib.parse import quote
        encoded_filename = quote(filename)
        
        logger.info(f"导出成功: {filename}, 共{len(chapters)}章, {len(final_content)}字符")
        
        return Response(
            content=final_content.encode('utf-8'),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Type": "text/plain; charset=utf-8"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出项目失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/{project_id}/check-consistency", summary="检查数据一致性")
async def check_project_consistency(
    project_id: str,
    request: Request,
    auto_fix: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    检查并修复项目的数据一致性问题
    
    Args:
        project_id: 项目ID
        auto_fix: 是否自动修复问题（默认True）
    
    返回检查报告，包含：
    - organization_records: 检查并修复缺失的Organization记录
    - member_counts: 检查并修复组织成员计数
    - relationships: 验证关系数据完整性
    - organization_members: 验证组织成员数据完整性
    """
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试检查数据一致性")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"开始数据一致性检查: project_id={project_id}, user_id={user_id}, auto_fix={auto_fix}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        report = await run_full_data_consistency_check(project_id, db, auto_fix)
        
        logger.info(f"数据一致性检查完成: {project_id}")
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"数据一致性检查失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"检查失败: {str(e)}")


@router.post("/{project_id}/fix-organizations", summary="修复组织记录")
async def fix_project_organizations(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    修复项目中缺失的Organization记录
    
    为所有is_organization=True但没有Organization记录的Character创建记录
    """
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试修复组织记录")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"开始修复组织记录: project_id={project_id}, user_id={user_id}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        fixed_count, total_count = await fix_missing_organization_records(project_id, db)
        
        logger.info(f"组织记录修复完成: {project_id}, 修复{fixed_count}/{total_count}")
        return {
            "message": "组织记录修复完成",
            "fixed": fixed_count,
            "total": total_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"修复组织记录失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"修复失败: {str(e)}")


@router.post("/{project_id}/fix-member-counts", summary="修复成员计数")
async def fix_project_member_counts(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    修复项目中所有组织的成员计数
    
    从实际成员记录重新计算每个组织的member_count
    """
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试修复成员计数")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"开始修复成员计数: project_id={project_id}, user_id={user_id}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        fixed_count, total_count = await fix_organization_member_counts(project_id, db)
        
        logger.info(f"成员计数修复完成: {project_id}, 修复{fixed_count}/{total_count}")
        return {
            "message": "成员计数修复完成",
            "fixed": fixed_count,
            "total": total_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"修复成员计数失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"修复失败: {str(e)}")


@router.post("/{project_id}/export-data", summary="导出项目数据为JSON")
async def export_project_data(
    project_id: str,
    request: Request,
    options: ExportOptions,
    db: AsyncSession = Depends(get_db)
):
    """
    导出项目完整数据为JSON格式
    
    Args:
        project_id: 项目ID
        options: 导出选项
            - include_generation_history: 是否包含生成历史
            - include_writing_styles: 是否包含写作风格
            - include_careers: 是否包含职业系统
            - include_memories: 是否包含故事记忆
            - include_plot_analysis: 是否包含剧情分析
    
    Returns:
        JSON文件下载
    """
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试导出项目数据")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"开始导出项目数据: project_id={project_id}, user_id={user_id}, options={options.model_dump()}")
        
        # 只查询当前用户的项目
        result = await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.user_id == user_id
            )
        )
        project = result.scalar_one_or_none()
        
        if not project:
            logger.warning(f"项目不存在或无权访问: project_id={project_id}, user_id={user_id}")
            raise HTTPException(status_code=404, detail="项目不存在")
        
        # 导出数据（使用所有选项）
        export_data = await ImportExportService.export_project(
            project_id=project_id,
            db=db,
            include_generation_history=options.include_generation_history,
            include_writing_styles=options.include_writing_styles,
            include_careers=options.include_careers,
            include_memories=options.include_memories,
            include_plot_analysis=options.include_plot_analysis
        )
        
        # 转换为JSON
        json_content = export_data.model_dump_json(indent=2, exclude_none=True, by_alias=True)
        
        # 生成文件名
        safe_title = "".join(c for c in project.title if c.isalnum() or c in (' ', '-', '_'))
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"project_{safe_title}_{date_str}.json"
        encoded_filename = quote(filename)
        
        logger.info(f"项目数据导出成功: {filename}")
        
        return Response(
            content=json_content.encode('utf-8'),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                "Content-Type": "application/json; charset=utf-8"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出项目数据失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.post("/validate-import", response_model=ImportValidationResult, summary="验证导入文件")
async def validate_import_file(
    file: UploadFile = File(...)
):
    """
    验证导入文件的格式和内容
    
    Args:
        file: 上传的JSON文件
    
    Returns:
        验证结果
    """
    try:
        logger.info(f"验证导入文件: {file.filename}")
        
        # 检查文件类型
        if not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail="只支持JSON格式文件")
        
        # 读取文件内容
        content = await file.read()
        
        # 检查文件大小（50MB限制）
        max_size = 50 * 1024 * 1024  # 50MB
        if len(content) > max_size:
            raise HTTPException(status_code=413, detail="文件大小超过50MB限制")
        
        # 解析JSON
        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"无效的JSON格式: {str(e)}")
        
        # 验证数据
        validation_result = ImportExportService.validate_import_data(data)
        
        logger.info(f"文件验证完成: valid={validation_result.valid}")
        return validation_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"验证导入文件失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"验证失败: {str(e)}")


@router.post("/import", response_model=ImportResult, summary="导入项目")
async def import_project(
    file: UploadFile = File(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    导入项目数据（创建新项目）
    
    Args:
        file: 上传的JSON文件
    
    Returns:
        导入结果
    """
    try:
        # 从认证中间件获取用户ID
        user_id = getattr(request.state, 'user_id', None)
        if not user_id:
            logger.warning("未登录用户尝试导入项目")
            raise HTTPException(status_code=401, detail="未登录")
        
        logger.info(f"开始导入项目: {file.filename}, user_id={user_id}")
        
        # 检查文件类型
        if not file.filename.endswith('.json'):
            raise HTTPException(status_code=400, detail="只支持JSON格式文件")
        
        # 读取文件内容
        content = await file.read()
        
        # 检查文件大小
        max_size = 50 * 1024 * 1024  # 50MB
        if len(content) > max_size:
            raise HTTPException(status_code=413, detail="文件大小超过50MB限制")
        
        # 解析JSON
        try:
            data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"无效的JSON格式: {str(e)}")
        
        # 导入数据（传入user_id）
        import_result = await ImportExportService.import_project(data, db, user_id)
        
        if import_result.success:
            logger.info(f"项目导入成功: {import_result.project_id}")
        else:
            logger.warning(f"项目导入失败: {import_result.message}")
        
        return import_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入项目失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")
