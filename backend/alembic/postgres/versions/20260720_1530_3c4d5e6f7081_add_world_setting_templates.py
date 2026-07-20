"""add world setting templates and dynamic project data

Revision ID: 3c4d5e6f7081
Revises: 1a2b3c4d5e6f
"""
from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "3c4d5e6f7081"
down_revision: Union[str, None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEMPLATES = [
    {
        "id": "10000000-0000-0000-0000-000000000001",
        "name": "修仙世界",
        "category": "玄幻",
        "fields": {
            "time_period": {"label": "时间设定", "type": "text", "required": True},
            "location": {"label": "地域与宗门", "type": "textarea", "required": True},
            "cultivation_levels": {"label": "修炼境界", "type": "list", "required": True},
            "power_system": {"label": "功法体系", "type": "textarea", "required": True},
            "rules": {"label": "天道规则", "type": "textarea", "required": True},
        },
        "example_data": {
            "time_period": "灵历九千八百年，旧天庭崩塌后的宗门时代",
            "location": "九州十三域，以中州仙盟与北境魔宗为两极",
            "cultivation_levels": ["炼气", "筑基", "金丹", "元婴", "化神"],
            "power_system": "修士以灵根引气，以功法塑造道基；术法会消耗灵力并留下因果代价。",
            "rules": "突破必须经历心魔与天劫；越阶使用力量会损伤道基。",
        },
    },
    {
        "id": "10000000-0000-0000-0000-000000000002",
        "name": "科幻世界",
        "category": "科幻",
        "fields": {
            "time_period": {"label": "时代", "type": "text", "required": True},
            "location": {"label": "星系与聚居地", "type": "textarea", "required": True},
            "technology_level": {"label": "科技等级", "type": "textarea", "required": True},
            "species": {"label": "种族与智能体", "type": "list", "required": False},
            "political_landscape": {"label": "政治格局", "type": "textarea", "required": True},
            "rules": {"label": "技术边界", "type": "textarea", "required": True},
        },
        "example_data": {
            "time_period": "公元 2478 年，第一次星门战争结束三十年后",
            "location": "人类活动范围横跨猎户臂七个殖民星系",
            "technology_level": "可控聚变与有限曲率航行成熟，强人工智能受条约监管。",
            "species": ["基准人类", "适应型改造人", "受限合成人"],
            "political_landscape": "地球联邦、边境自治领与企业共同体维持脆弱平衡。",
            "rules": "超光速通信不可用；星门跳跃需要精确质量配平。",
        },
    },
    {
        "id": "10000000-0000-0000-0000-000000000003",
        "name": "现代都市",
        "category": "现代",
        "fields": {
            "time_period": {"label": "时间设定", "type": "text", "required": True},
            "location": {"label": "城市与区域", "type": "textarea", "required": True},
            "social_background": {"label": "社会背景", "type": "textarea", "required": True},
            "economic_setting": {"label": "经济与行业", "type": "textarea", "required": False},
            "atmosphere": {"label": "城市氛围", "type": "textarea", "required": False},
        },
        "example_data": {
            "time_period": "当代，移动互联网高度普及的近年",
            "location": "沿海新一线城市，故事集中在老城区与科技园",
            "social_background": "人口流动频繁，传统社区与新产业并存。",
            "economic_setting": "平台经济降温，人工智能创业潮兴起。",
            "atmosphere": "快节奏表面下保留邻里关系与城市记忆。",
        },
    },
    {
        "id": "10000000-0000-0000-0000-000000000004",
        "name": "西方奇幻",
        "category": "奇幻",
        "fields": {
            "time_period": {"label": "纪元", "type": "text", "required": True},
            "location": {"label": "大陆与王国", "type": "textarea", "required": True},
            "magic_system": {"label": "魔法体系", "type": "textarea", "required": True},
            "species": {"label": "种族", "type": "list", "required": False},
            "kingdoms": {"label": "王国与势力", "type": "list", "required": True},
            "rules": {"label": "世界法则", "type": "textarea", "required": True},
        },
        "example_data": {
            "time_period": "王冠纪元 612 年，龙灾结束后的第二代和平",
            "location": "埃尔达大陆被灰脊山脉分为东西诸国",
            "magic_system": "法师通过契约借用元素位面力量，每次施法都会积累对应元素侵蚀。",
            "species": ["人类", "森灵", "石裔", "龙裔"],
            "kingdoms": ["洛伦王国", "北境自由城邦", "赤金教廷"],
            "rules": "真名具有约束力；复活只能在灵魂尚未渡过冥河前进行。",
        },
    },
]


def upgrade() -> None:
    op.add_column("projects", sa.Column("world_setting_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_table(
        "world_setting_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("example_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_world_setting_templates_user_id"), "world_setting_templates", ["user_id"], unique=False)
    op.create_index(op.f("ix_world_setting_templates_category"), "world_setting_templates", ["category"], unique=False)
    op.create_index("ix_world_setting_templates_category_system", "world_setting_templates", ["category", "is_system"], unique=False)

    for item in TEMPLATES:
        fields_json = json.dumps(item["fields"], ensure_ascii=False).replace("'", "''")
        examples_json = json.dumps(item["example_data"], ensure_ascii=False).replace("'", "''")
        template_id = item["id"].replace("'", "''")
        name = item["name"].replace("'", "''")
        category = item["category"].replace("'", "''")
        op.execute(
            f"INSERT INTO world_setting_templates "
            f"(id, user_id, name, category, fields, example_data, is_system) VALUES "
            f"('{template_id}', NULL, '{name}', '{category}', '{fields_json}'::jsonb, '{examples_json}'::jsonb, true)"
        )

    legacy_fields = json.dumps({
        "time_period": {"label": "时间设定", "type": "textarea", "required": False},
        "location": {"label": "地点设定", "type": "textarea", "required": False},
        "atmosphere": {"label": "氛围设定", "type": "textarea", "required": False},
        "rules": {"label": "规则设定", "type": "textarea", "required": False},
    }, ensure_ascii=False).replace("'", "''")
    op.execute(
        "UPDATE projects SET world_setting_data = jsonb_build_object("
        "'template_id', NULL, 'template_name', '旧版世界设定', "
        f"'fields', '{legacy_fields}'::jsonb, "
        "'values', jsonb_strip_nulls(jsonb_build_object("
        "'time_period', world_time_period, 'location', world_location, "
        "'atmosphere', world_atmosphere, 'rules', world_rules))) "
        "WHERE COALESCE(world_time_period, '') <> '' OR COALESCE(world_location, '') <> '' "
        "OR COALESCE(world_atmosphere, '') <> '' OR COALESCE(world_rules, '') <> ''"
    )


def downgrade() -> None:
    op.drop_index("ix_world_setting_templates_category_system", table_name="world_setting_templates")
    op.drop_index(op.f("ix_world_setting_templates_category"), table_name="world_setting_templates")
    op.drop_index(op.f("ix_world_setting_templates_user_id"), table_name="world_setting_templates")
    op.drop_table("world_setting_templates")
    op.drop_column("projects", "world_setting_data")
