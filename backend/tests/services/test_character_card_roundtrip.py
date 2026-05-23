from __future__ import annotations

# pyright: reportAny=false, reportImplicitRelativeImport=false, reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Character, Project
from app.services.import_export_service import ImportExportService


USER_ID = "user-character-card-service"
SOURCE_PROJECT_ID = "project-character-card-source"
TARGET_PROJECT_ID = "project-character-card-target"


def test_round_trip_preserves_writing_fields(async_db_session: async_sessionmaker[AsyncSession]) -> None:
    async def run() -> None:
        async with async_db_session() as db:
            db.add(Project(id=SOURCE_PROJECT_ID, user_id=USER_ID, title="源项目"))
            db.add(Project(id=TARGET_PROJECT_ID, user_id=USER_ID, title="目标项目"))
            db.add(
                Character(
                    id="character-card-source",
                    project_id=SOURCE_PROJECT_ID,
                    name="林照夜",
                    age="19",
                    gender="女",
                    role_type="protagonist",
                    personality="克制、敏锐",
                    background="流亡王女",
                    appearance="银发黑瞳",
                    traits='["冷静", "守信"]',
                    writing_notes="只给作者看的秘密：她知道火种真相。",
                    speech_patterns="短句，少用感叹号，称呼主角为‘先生’。",
                    motivations="夺回王城并保护幸存者。",
                    arc_summary="从复仇执念转为承担王者责任。",
                    card_version=1,
                )
            )
            await db.commit()

            exported = await ImportExportService.export_characters(["character-card-source"], db)
            exported_card = exported["data"][0]
            assert exported["version"] == "1.2.0"
            assert exported_card["writing_notes"] == "只给作者看的秘密：她知道火种真相。"
            assert exported_card["speech_patterns"] == "短句，少用感叹号，称呼主角为‘先生’。"
            assert exported_card["motivations"] == "夺回王城并保护幸存者。"
            assert exported_card["arc_summary"] == "从复仇执念转为承担王者责任。"
            assert exported_card["card_version"] == 1

            imported = await ImportExportService.import_characters(exported, TARGET_PROJECT_ID, USER_ID, db)
            assert imported["success"] is True
            assert imported["statistics"]["imported"] == 1

            result = await db.execute(
                select(Character).where(Character.project_id == TARGET_PROJECT_ID, Character.name == "林照夜")
            )
            imported_character = result.scalar_one()
            assert imported_character.writing_notes == "只给作者看的秘密：她知道火种真相。"
            assert imported_character.speech_patterns == "短句，少用感叹号，称呼主角为‘先生’。"
            assert imported_character.motivations == "夺回王城并保护幸存者。"
            assert imported_character.arc_summary == "从复仇执念转为承担王者责任。"
            assert imported_character.card_version == 1

    asyncio.run(run())


def test_character_card_import_validation_rejects_malformed_payload() -> None:
    malformed = {
        "version": "1.2.0",
        "export_type": "characters",
        "data": [
            {
                "name": "坏角色",
                "is_organization": False,
                "writing_notes": {"not": "text"},
                "card_version": 0,
            }
        ],
    }

    validation = ImportExportService.validate_characters_import(malformed)

    assert validation["valid"] is False
    assert "第1个角色的writing_notes字段必须是字符串" in validation["errors"]
    assert "第1个角色的card_version字段必须是大于等于1的整数" in validation["errors"]
