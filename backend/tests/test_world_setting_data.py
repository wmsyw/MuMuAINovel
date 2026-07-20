from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.world_setting_templates import _normalize_values
from app.schemas.world_setting_template import WorldSettingFieldDefinition
from app.services.import_export_service import ImportExportService
from app.services.world_setting_data_service import (
    dynamic_world_setting_context,
    normalize_world_setting_data,
)


def test_template_validation_rejects_whitespace_text_and_empty_required_list() -> None:
    definitions = {
        "era": WorldSettingFieldDefinition(label="时代", type="text", required=True),
        "laws": WorldSettingFieldDefinition(label="法则", type="list", required=True),
    }

    with pytest.raises(HTTPException) as text_error:
        _normalize_values(definitions, {"era": " \t", "laws": ["契约"]})
    assert text_error.value.status_code == 422

    with pytest.raises(HTTPException) as list_error:
        _normalize_values(definitions, {"era": "远古时代", "laws": [" ", "\n"]})
    assert list_error.value.status_code == 422


def test_dynamic_values_are_trimmed_and_reach_prompt_context() -> None:
    project = SimpleNamespace(
        world_time_period="旧纪元",
        world_location="旧都",
        world_atmosphere="克制",
        world_rules="灯不灭",
        world_setting_data={
            "template_id": "template-1",
            "template_name": "科幻扩展",
            "fields": {
                "time_period": {"label": "时代", "type": "text", "required": False},
                "star_gate": {"label": "星门规则", "type": "textarea", "required": True},
                "species": {"label": "种族", "type": "list", "required": False},
            },
            "values": {
                "time_period": " 旧纪元 ",
                "star_gate": " 只能单向跃迁 ",
                "species": [" 人类 ", "", "改造人 "],
            },
        },
    )

    normalized = normalize_world_setting_data(
        project.world_setting_data,
        legacy_values={
            "world_time_period": project.world_time_period,
            "world_location": project.world_location,
            "world_atmosphere": project.world_atmosphere,
            "world_rules": project.world_rules,
        },
        require_required=True,
    )
    assert normalized["values"]["star_gate"] == "只能单向跃迁"
    assert normalized["values"]["species"] == ["人类", "改造人"]

    prompt_context = dynamic_world_setting_context(project)
    assert "星门规则" in prompt_context
    assert "只能单向跃迁" in prompt_context
    assert "species" in prompt_context


def test_import_validation_rejects_invalid_required_dynamic_values() -> None:
    data = {
        "version": "1.2.0",
        "project": {
            "title": "动态世界",
            "world_setting_data": {
                "template_id": "template-1",
                "template_name": "必填模板",
                "fields": {
                    "era": {"label": "时代", "type": "text", "required": True},
                    "laws": {"label": "法则", "type": "list", "required": True},
                },
                "values": {"era": " ", "laws": []},
            },
        },
    }

    validation = ImportExportService.validate_import_data(data)
    assert validation.valid is False
    assert any("动态世界设定无效" in error for error in validation.errors)


def test_import_validation_accepts_lossless_dynamic_metadata() -> None:
    dynamic_data = {
        "template_id": "template-1",
        "template_name": "扩展模板",
        "fields": {
            "era": {"label": "时代", "type": "text", "required": True},
            "currency": {"label": "货币", "type": "list", "required": False},
        },
        "values": {"era": "未来", "currency": ["信用点", "能源券"]},
    }
    data = {
        "version": "1.2.0",
        "project": {
            "title": "动态世界",
            "world_time_period": "未来",
            "world_setting_data": dynamic_data,
        },
    }

    validation = ImportExportService.validate_import_data(data)
    assert validation.valid is True
    normalized = normalize_world_setting_data(
        dynamic_data,
        legacy_values={"world_time_period": "未来"},
        require_required=True,
    )
    assert normalized["template_id"] == dynamic_data["template_id"]
    assert normalized["template_name"] == dynamic_data["template_name"]
    assert normalized["fields"]["currency"] == dynamic_data["fields"]["currency"]
    assert normalized["values"]["currency"] == dynamic_data["values"]["currency"]
