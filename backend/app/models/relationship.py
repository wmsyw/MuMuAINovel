"""角色关系和组织管理数据模型"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Float, JSON, Index
from sqlalchemy.sql import func
from app.database import Base
import uuid


class RelationshipType(Base):
    """关系类型定义表"""
    __tablename__ = "relationship_types"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="关系名称")
    category = Column(String(20), nullable=False, comment="分类：family/social/hostile/professional")
    reverse_name = Column(String(50), comment="反向关系名称")
    intimacy_range = Column(String(20), comment="亲密度范围：high/medium/low")
    icon = Column(String(50), comment="图标标识")
    description = Column(Text, comment="关系描述")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    
    def __repr__(self):
        return f"<RelationshipType(id={self.id}, name={self.name}, category={self.category})>"


class CharacterRelationship(Base):
    """角色关系表"""
    __tablename__ = "character_relationships"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="关系ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    
    # 关系双方
    character_from_id = Column(String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True, comment="角色A的ID")
    character_to_id = Column(String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True, comment="角色B的ID")
    
    # 关系类型
    relationship_type_id = Column(Integer, ForeignKey("relationship_types.id"), index=True, comment="关系类型ID")
    relationship_name = Column(String(100), comment="自定义关系名称")
    
    # 关系属性
    intimacy_level = Column(Integer, default=50, comment="亲密度：-100到100")
    status = Column(String(20), default="active", comment="状态：active/broken/past/complicated")
    description = Column(Text, comment="关系详细描述")
    
    # 故事时间线
    started_at = Column(String(100), comment="关系开始时间（故事时间）")
    ended_at = Column(String(100), comment="关系结束时间（故事时间）")
    
    # 来源标识
    source = Column(String(20), default="ai", comment="来源：ai/manual/imported")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    def __repr__(self):
        return f"<CharacterRelationship(id={self.id}, from={self.character_from_id}, to={self.character_to_id})>"


class EntityRelationship(Base):
    """支持角色和组织端点的一等实体关系表。"""
    __tablename__ = "entity_relationships"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="实体关系ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    from_entity_type = Column(String(20), nullable=False, comment="起点类型：character/organization")
    from_entity_id = Column(String(36), nullable=False, comment="起点实体ID")
    to_entity_type = Column(String(20), nullable=False, comment="终点类型：character/organization")
    to_entity_id = Column(String(36), nullable=False, comment="终点实体ID")
    relationship_type_id = Column(Integer, ForeignKey("relationship_types.id"), index=True, comment="关系类型ID")
    relationship_name = Column(String(100), comment="自定义关系名称")
    intimacy_level = Column(Integer, default=50, comment="亲密度：-100到100")
    status = Column(String(20), default="active", server_default="active", nullable=False, comment="状态：active/broken/past/complicated")
    description = Column(Text, comment="关系详细描述")
    started_at = Column(String(100), comment="关系开始时间（故事时间）")
    ended_at = Column(String(100), comment="关系结束时间（故事时间）")
    source = Column(String(20), default="ai", comment="来源：ai/manual/imported/legacy")
    legacy_character_relationship_id = Column(String(36), unique=True, index=True, comment="迁移前角色关系ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_entity_relationships_project_status", "project_id", "status"),
        Index("idx_entity_relationships_from", "from_entity_type", "from_entity_id"),
        Index("idx_entity_relationships_to", "to_entity_type", "to_entity_id"),
    )


class Organization(Base):
    """组织详情旧表桥接记录（详情字段已吸收到 OrganizationEntity）。"""
    __tablename__ = "organizations"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="组织ID")
    character_id = Column(String(36), nullable=True, unique=True, comment="迁移前关联的组织角色ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    organization_entity_id = Column(String(36), ForeignKey("organization_entities.id", ondelete="SET NULL"), unique=True, index=True, comment="拆分后的组织实体ID")
    
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    def __repr__(self):
        return f"<Organization(id={self.id}, character_id={self.character_id})>"


class OrganizationMember(Base):
    """组织成员关系表"""
    __tablename__ = "organization_members"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="成员关系ID")
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="SET NULL"), index=True, comment="迁移前组织ID")
    organization_entity_id = Column(String(36), ForeignKey("organization_entities.id", ondelete="CASCADE"), nullable=False, index=True, comment="组织实体ID")
    character_id = Column(String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True, comment="角色ID")
    
    # 职位信息
    position = Column(String(100), nullable=False, comment="职位名称")
    rank = Column(Integer, default=0, comment="职位等级")
    
    # 成员状态
    status = Column(String(20), default="active", comment="状态：active/retired/expelled/deceased")
    joined_at = Column(String(100), comment="加入时间（故事时间）")
    left_at = Column(String(100), comment="离开时间（故事时间）")
    
    # 成员属性
    loyalty = Column(Integer, default=50, comment="忠诚度：0-100")
    contribution = Column(Integer, default=0, comment="贡献度：0-100")
    
    # 来源标识
    source = Column(String(20), default="ai", comment="来源：ai/manual")
    
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    def __repr__(self):
        return f"<OrganizationMember(id={self.id}, org={self.organization_id}, char={self.character_id})>"


class OrganizationEntity(Base):
    """一等组织实体表。"""
    __tablename__ = "organization_entities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="组织实体ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")

    name = Column(String(100), nullable=False, comment="组织名称")
    normalized_name = Column(String(100), nullable=False, comment="规范化组织名称")
    personality = Column(Text, comment="组织特性")
    background = Column(Text, comment="组织背景")
    current_state = Column(Text, comment="组织当前状态")
    avatar_url = Column(String(500), comment="头像URL")
    traits = Column(Text, comment="特征标签(JSON)")
    organization_type = Column(String(100), comment="组织类型")
    organization_purpose = Column(String(500), comment="组织目的")
    status = Column(String(20), default="active", server_default="active", nullable=False, comment="状态：active/destroyed/dormant/retired")
    parent_org_id = Column(String(36), ForeignKey("organization_entities.id", ondelete="SET NULL"), index=True, comment="父组织实体ID")
    legacy_parent_org_id = Column(String(36), comment="迁移前父组织ID")
    level = Column(Integer, default=0, comment="组织层级")
    power_level = Column(Integer, default=50, comment="势力等级：0-100")
    member_count = Column(Integer, default=0, comment="成员数量")
    location = Column(Text, comment="所在地")
    motto = Column(String(200), comment="宗旨/口号")
    color = Column(String(100), comment="代表颜色")

    legacy_character_id = Column(String(36), unique=True, index=True, comment="迁移前承载组织的角色ID")
    legacy_organization_id = Column(String(36), unique=True, index=True, comment="迁移前组织详情记录ID")
    source = Column(String(20), default="legacy", server_default="legacy", nullable=False, comment="来源：legacy/manual/ai/imported")

    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_org_entities_project_name", "project_id", "normalized_name"),
        Index("idx_org_entities_project_status", "project_id", "status"),
    )

    def __repr__(self):
        return f"<OrganizationEntity(id={self.id}, name={self.name})>"


class ExtractionRun(Base):
    """章节/项目正文抽取运行记录。"""
    __tablename__ = "extraction_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="抽取运行ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="章节ID")

    trigger_source = Column(String(50), nullable=False, comment="触发来源：chapter_save/manual/import等")
    pipeline_version = Column(String(50), nullable=False, comment="抽取管线版本")
    schema_version = Column(String(50), nullable=False, comment="结构化输出Schema版本")
    prompt_hash = Column(String(128), comment="提示词哈希")
    content_hash = Column(String(128), nullable=False, comment="正文内容哈希")
    status = Column(String(20), default="pending", server_default="pending", nullable=False, comment="状态：pending/running/completed/failed/cancelled")

    provider = Column(String(50), comment="AI提供商")
    model = Column(String(100), comment="模型名称")
    reasoning_intensity = Column(String(20), comment="推理强度")
    raw_response = Column(JSON, comment="模型原始响应")
    run_metadata = Column("metadata", JSON, comment="运行元数据")
    error_message = Column(Text, comment="错误信息")
    started_at = Column(DateTime, comment="开始时间")
    completed_at = Column(DateTime, comment="完成时间")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_extraction_runs_project_status", "project_id", "status"),
        Index("idx_extraction_runs_project_content", "project_id", "chapter_id", "content_hash", "schema_version", "prompt_hash"),
    )


class ExtractionCandidate(Base):
    """抽取得到、等待评审/合并的候选事实。"""
    __tablename__ = "extraction_candidates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="候选ID")
    run_id = Column(String(36), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True, comment="抽取运行ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    user_id = Column(String(100), nullable=False, index=True, comment="用户ID")
    source_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="来源章节ID")
    source_chapter_start_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="来源章节范围起点")
    source_chapter_end_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="来源章节范围终点")

    candidate_type = Column(String(50), nullable=False, comment="候选类型：character/organization/relationship/world_fact等")
    trigger_type = Column(String(50), nullable=False, comment="触发类型：manual/chapter_save/import等")
    source_hash = Column(String(128), nullable=False, comment="来源文本/范围哈希")
    provider = Column(String(50), comment="AI提供商快照")
    model = Column(String(100), comment="模型快照")
    reasoning_intensity = Column(String(20), comment="推理强度快照")
    display_name = Column(String(200), comment="展示名称")
    normalized_name = Column(String(200), comment="规范化名称")
    canonical_target_type = Column(String(20), comment="目标类型：character/organization/career")
    canonical_target_id = Column(String(36), comment="目标规范实体ID")
    status = Column(String(20), default="pending", server_default="pending", nullable=False, comment="状态：pending/accepted/rejected/merged/superseded")
    confidence = Column(Float, nullable=False, comment="置信度")

    evidence_text = Column(Text, nullable=False, comment="证据原文")
    source_start_offset = Column(Integer, nullable=False, comment="证据起始字符偏移")
    source_end_offset = Column(Integer, nullable=False, comment="证据结束字符偏移")
    source_chapter_number = Column(Integer, comment="来源章节序号")
    source_chapter_order = Column(Integer, comment="来源章节内顺序")
    valid_from_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="事实有效起点章节")
    valid_from_chapter_order = Column(Integer, comment="事实有效起点章节内顺序")
    valid_to_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="事实有效终点章节")
    valid_to_chapter_order = Column(Integer, comment="事实有效终点章节内顺序")
    story_time_label = Column(String(100), comment="故事内时间标签")
    payload = Column(JSON, nullable=False, comment="规范化候选载荷")
    raw_payload = Column(JSON, comment="模型原始候选载荷")

    merge_target_type = Column(String(50), comment="合并目标类型")
    merge_target_id = Column(String(36), comment="合并目标ID")
    reviewer_user_id = Column(String(100), comment="评审用户ID")
    reviewed_at = Column(DateTime, comment="评审时间")
    accepted_at = Column(DateTime, comment="接受时间")
    rejection_reason = Column(Text, comment="拒绝原因")
    supersedes_candidate_id = Column(String(36), ForeignKey("extraction_candidates.id", ondelete="SET NULL"), comment="被替代候选ID")
    rollback_of_candidate_id = Column(String(36), ForeignKey("extraction_candidates.id", ondelete="SET NULL"), comment="回滚的候选ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_extraction_candidates_run_status", "run_id", "status"),
        Index("idx_extraction_candidates_project_type_status", "project_id", "candidate_type", "status"),
        Index("idx_extraction_candidates_source_hash", "project_id", "source_hash"),
        Index("idx_extraction_candidates_canonical", "canonical_target_type", "canonical_target_id"),
        Index("idx_extraction_candidates_timeline", "project_id", "valid_from_chapter_id", "valid_from_chapter_order"),
    )


class EntityProvenance(Base):
    """规范实体/事实的来源证据。"""
    __tablename__ = "entity_provenance"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="来源ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    entity_type = Column(String(50), nullable=False, comment="实体类型")
    entity_id = Column(String(36), nullable=False, comment="实体ID")

    source_type = Column(String(50), nullable=False, comment="来源类型：extraction_candidate/legacy_existing_record/manual/imported")
    source_id = Column(String(36), comment="来源记录ID")
    run_id = Column(String(36), ForeignKey("extraction_runs.id", ondelete="SET NULL"), index=True, comment="抽取运行ID")
    candidate_id = Column(String(36), ForeignKey("extraction_candidates.id", ondelete="SET NULL"), index=True, comment="候选ID")
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="章节ID")

    claim_type = Column(String(50), nullable=False, comment="事实类型")
    claim_payload = Column(JSON, comment="事实载荷")
    evidence_text = Column(Text, comment="证据原文")
    source_start = Column(Integer, comment="证据起始字符偏移")
    source_end = Column(Integer, comment="证据结束字符偏移")
    confidence = Column(Float, comment="置信度")
    status = Column(String(20), default="active", server_default="active", nullable=False, comment="状态：active/superseded/rolled_back")
    created_by = Column(String(100), comment="创建用户/系统")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_entity_provenance_entity", "entity_type", "entity_id"),
        Index("idx_entity_provenance_project_claim", "project_id", "claim_type", "status"),
    )


class EntityAlias(Base):
    """规范实体别名。"""
    __tablename__ = "entity_aliases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="别名ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    entity_type = Column(String(50), nullable=False, comment="实体类型")
    entity_id = Column(String(36), nullable=False, comment="实体ID")
    alias = Column(String(200), nullable=False, comment="别名")
    normalized_alias = Column(String(200), nullable=False, comment="规范化别名")
    source = Column(String(50), default="manual", server_default="manual", nullable=False, comment="来源")
    provenance_id = Column(String(36), ForeignKey("entity_provenance.id", ondelete="SET NULL"), index=True, comment="来源ID")
    status = Column(String(20), default="active", server_default="active", nullable=False, comment="状态：active/retired")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_entity_aliases_lookup", "project_id", "normalized_alias", "entity_type"),
        Index("idx_entity_aliases_entity", "entity_type", "entity_id", "status"),
    )


class RelationshipTimelineEvent(Base):
    """关系、组织归属和职业变化的章节时间线事件。"""
    __tablename__ = "relationship_timeline_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="时间线事件ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    relationship_id = Column(String(36), ForeignKey("entity_relationships.id", ondelete="SET NULL"), index=True, comment="实体关系ID")
    organization_member_id = Column(String(36), ForeignKey("organization_members.id", ondelete="SET NULL"), index=True, comment="组织成员关系ID")
    character_id = Column(String(36), ForeignKey("characters.id", ondelete="SET NULL"), index=True, comment="主体角色ID")
    related_character_id = Column(String(36), ForeignKey("characters.id", ondelete="SET NULL"), index=True, comment="相关角色ID")
    organization_entity_id = Column(String(36), ForeignKey("organization_entities.id", ondelete="SET NULL"), index=True, comment="组织实体ID")
    career_id = Column(String(36), ForeignKey("careers.id", ondelete="SET NULL"), index=True, comment="职业ID")

    event_type = Column(String(50), nullable=False, comment="事件类型：relationship/affiliation/profession/status")
    event_status = Column(String(20), default="active", server_default="active", nullable=False, comment="状态：active/ended/superseded/rolled_back")
    relationship_name = Column(String(100), comment="关系名称")
    position = Column(String(100), comment="组织职位")
    rank = Column(Integer, comment="职位/等级")
    career_stage = Column(Integer, comment="职业阶段")
    story_time_label = Column(String(100), comment="故事内时间标签")

    source_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="来源章节ID")
    source_chapter_order = Column(Integer, comment="来源章节内顺序")
    valid_from_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="有效起点章节")
    valid_from_chapter_order = Column(Integer, comment="有效起点章节内顺序")
    valid_to_chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="SET NULL"), index=True, comment="有效终点章节")
    valid_to_chapter_order = Column(Integer, comment="有效终点章节内顺序")
    source_start_offset = Column(Integer, comment="证据起始字符偏移")
    source_end_offset = Column(Integer, comment="证据结束字符偏移")
    evidence_text = Column(Text, comment="证据原文")
    confidence = Column(Float, comment="置信度")
    provenance_id = Column(String(36), ForeignKey("entity_provenance.id", ondelete="SET NULL"), index=True, comment="来源ID")
    supersedes_event_id = Column(String(36), ForeignKey("relationship_timeline_events.id", ondelete="SET NULL"), comment="被替代事件ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    __table_args__ = (
        Index("idx_relationship_timeline_project_position", "project_id", "valid_from_chapter_id", "valid_from_chapter_order"),
        Index("idx_relationship_timeline_type_status", "project_id", "event_type", "event_status"),
    )


class WorldSettingResult(Base):
    """世界观生成结果历史；Project.world_* 仍是当前活跃快照。"""
    __tablename__ = "world_setting_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="世界观结果ID")
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID")
    run_id = Column(String(36), ForeignKey("extraction_runs.id", ondelete="SET NULL"), index=True, comment="相关抽取/生成运行ID")
    status = Column(String(20), default="pending", server_default="pending", nullable=False, comment="状态：pending/accepted/rejected/superseded/rolled_back")

    world_time_period = Column(Text, comment="时间背景")
    world_location = Column(Text, comment="地理位置")
    world_atmosphere = Column(Text, comment="氛围基调")
    world_rules = Column(Text, comment="世界规则")
    prompt = Column(Text, comment="生成提示词")
    provider = Column(String(50), comment="AI提供商")
    model = Column(String(100), comment="模型名称")
    reasoning_intensity = Column(String(20), comment="推理强度")
    raw_result = Column(JSON, comment="原始结果")
    source_type = Column(String(50), default="ai", server_default="ai", nullable=False, comment="来源类型：ai/manual/legacy")
    accepted_at = Column(DateTime, comment="接受时间")
    accepted_by = Column(String(100), comment="接受用户ID")
    supersedes_result_id = Column(String(36), ForeignKey("world_setting_results.id", ondelete="SET NULL"), comment="被替代结果ID")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_world_setting_results_project_status", "project_id", "status"),
        Index("idx_world_setting_results_project_created", "project_id", "created_at"),
    )
