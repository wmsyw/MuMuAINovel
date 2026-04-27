# MuMuAINovel Novel Workflow and Provider Refactor

## TL;DR
> **Summary**: Refactor MuMuAINovel from manually/AI-generated isolated writing assets into an extraction-driven canon system where persisted 正文 is the source of truth for characters, organizations, professions, relationships, and world facts. Split Character/Organization into independent first-class tables. Add OpenAI Responses API support and provider/model-gated thinking intensity configuration for OpenAI, Claude, and Gemini. Use `EXTRACTION_PIPELINE_ENABLED` feature flag for progressive rollout.
> **Deliverables**:
> - Additive extraction/candidate/provenance/timeline/world-setting-result data model with SQLite and PostgreSQL migrations, including Character/Organization table split.
> - Automatic + manual 正文 extraction pipeline with review, accept, reject, merge, rollback, dedupe, and full chapter-based timeline support, gated by `EXTRACTION_PIPELINE_ENABLED` feature flag.
> - Default policy gate disabling AI-generated character/organization/profession creation, with backend-enforced advanced/admin override and audit metadata.
> - World-setting generation result history separated from active `Project.world_*` snapshot.
> - OpenAI Responses API adapter behind the existing AI provider abstraction (new methods in `OpenAIClient`, routing in `OpenAIProvider`).
> - Data-driven provider/model capability registry for normalized reasoning intensity across OpenAI, Claude, Gemini, with unknown-model fallback.
> - Minimal backend/frontend automated test infrastructure plus build/lint/Docker smoke verification.
> **Effort**: XL
> **Parallel**: YES - 4 execution waves + final verification wave
> **Critical Path**: Task 1 → Task 2 → Task 6 → Task 7 → Task 10b → Task 14/16 → Task 17 → Task 18 → F1-F4

## Context
### Original Request
- 用户需要对项目进行功能重构，主要涉及“灵感模式重构、世界设定生成逻辑与结果重构、角色与组织管理功能重构、职业管理重构”。
- 角色、组织、职业“默认不允许新增生成，应当从正文中自动提取并整合关系”。
- 重构方向需要参考 GitHub 上类似项目，目标先分析 20 个类似项目并按 star 数排序。
- 增加 OpenAI Responses API 支持。
- 增加思考强度配置支持，OpenAI、Claude、Gemini 各模型支持的思考强度等级需先查询清楚。

### Interview Summary
- Extraction trigger: **自动+手动**. Run extraction after persisted 正文 save, generated chapter persistence, and TXT import completion; also expose manual project/chapter/range re-extract and merge.
- AI entity generation restriction: **高级开关**. Ordinary/default workflows must not AI-generate canonical characters/organizations/professions. Backend-enforced advanced/admin override may enable legacy generation, with audit metadata. Manual correction/editing remains allowed.
- Data migration: **保留并迁移**. Preserve existing characters, organizations, careers/professions, relationships, and world settings; add provenance/confidence/timeline/versioning and allow post-migration extraction to merge/dedupe.
- Tests: **补测试基建**. Add minimal automated backend/frontend testing because the repo currently has no formal pytest/vitest/jest suite.
- Relationship granularity: **完整时间线**. Relationships, professions, and organization affiliations must be versioned across chapters/time spans, not flattened to only current state.

### Research Summary
#### Local code anchors
- `backend/app/main.py:27-55,130-161,163-203` — app lifespan, router registration, SPA fallback.
- `backend/app/api/inspiration.py:13-243` + `frontend/src/pages/Inspiration.tsx:51-260` — current inspiration mode.
- `backend/app/api/wizard_stream.py:41-231,1380-1520,1551-1639` — SSE project wizard, outline/character/org post-processing, world regen.
- `backend/app/api/outlines.py:58-158,720-981,984-1039` — outline CRUD, generation, auto-created missing characters/orgs.
- `backend/app/api/characters.py:34-260`, `organizations.py:36-260`, `careers.py:36-260` — CRUD plus generation entrypoints to gate/refactor.
- `backend/app/api/book_import.py:30-282` and `backend/app/services/book_import_service.py:644-1759` — TXT import and reverse extraction path.
- `backend/app/services/auto_character_service.py:17-260,549-557` and `auto_organization_service.py:17-260,457-465` — outline-derived auto creation.
- `backend/app/services/character_state_update_service.py:1-260` — existing chapter-analysis-driven character state/relationship updates; must be replaced/absorbed by append-only timeline/provenance model.
- `backend/app/services/ai_clients/openai_client.py:11-175` and `backend/app/services/ai_providers/openai_provider.py:11-174` — current OpenAI chat-completions path; no Responses API.
- `backend/app/api/settings.py:102-1297`, `backend/app/models/settings.py:8-53`, `backend/app/schemas/settings.py:7-143`, `frontend/src/pages/Settings.tsx:13-2050` — provider/model/settings UI/API surface.
- `backend/app/models/project.py:8-55`, `character.py:8-57`, `relationship.py:8-116`, `career.py:8-77` — current persistence surfaces.
- `frontend/src/services/api.ts:69-150,222-260,922-1087`, `frontend/src/types/index.ts:221-479,998-1181` — frontend API/types integration points.
- `frontend/package.json:1-45` — current scripts: build/lint/dev/preview, no test script.
- `docker-compose.yml:1-140`, `Dockerfile:1-123` — Docker-first smoke path and `/health` check.

#### Similar GitHub projects analyzed
Top 20 relevant repositories sorted by stars: `SillyTavern/SillyTavern` (26,294★), `YILING0013/AI_NovelGenerator` (4,496★), `KoboldAI/KoboldAI-Client` (3,879★), `kwaroran/Risuai` (1,421★), `mind-protocol/terminal-velocity` (1,099★), `HappyFox001/AI-Chat` (808★), `ExplosiveCoderflome/AI-Novel-Writing-Assistant` (743★), `jofizcd/Soul-of-Waifu` (642★), `josephrocca/OpenCharacters` (395★), `vishiri/fantasia-archive` (388★), `mak-kirkland/chronicler` (275★), `Pasta-Devs/Marinara-Engine` (216★), `aikohanasaki/SillyTavern-MemoryBooks` (188★), `ypcypc/WhatIf` (174★), `alienet1109/BookWorld` (169★), `doolijb/serene-pub` (166★), `aomukai/Writingway` (152★), `bmen25124/SillyTavern-Character-Creator` (138★), `AventurasTeam/Aventuras` (135★), `raestrada/storycraftr` (129★).

Patterns to adopt: staged writing workflows, canon/lorebook separate from chat, structured entity data, extraction/compression from prose, provider/model config as first-class UX, specialized consistency/research/editing services instead of one monolithic prompt.

#### Reasoning/thinking API research
- OpenAI Responses API: `reasoning.effort`, generic values `none|minimal|low|medium|high|xhigh` with model-specific subsets/defaults. Use `previous_response_id` or reasoning item pass-through for tool-call turns. Docs: `https://developers.openai.com/api/docs/guides/reasoning`, `https://developers.openai.com/api/docs/api-reference/responses/create`.
- Claude: `thinking.type`, `thinking.display`, `thinking.budget_tokens`, `output_config.effort`; effort values `low|medium|high|xhigh|max` with model-specific support. Docs: `https://docs.anthropic.com/en/docs/build-with-claude/adaptive-thinking`, `https://docs.anthropic.com/en/docs/build-with-claude/effort`.
- Gemini: Gemini 3 uses `thinkingConfig.thinkingLevel`; Gemini 2.5 uses numeric `thinkingConfig.thinkingBudget`; `thinkingLevel` and `thinkingBudget` are mutually exclusive; thought signatures must be preserved for multi-turn/function-calling continuity. Docs: `https://ai.google.dev/gemini-api/docs/thinking`, `https://cloud.google.com/vertex-ai/generative-ai/docs/thinking`.

### Metis Review (gaps addressed)
- Use append-only extraction runs/candidates/provenance/timeline edges with derived current projections.
- Keep existing flat/current tables usable during compatibility transition.
- **Split Character/Organization into independent first-class tables**: current `Character.is_organization` pattern replaced by dedicated `Organization` entity table (not the current `organizations` detail table which is a child of `characters`). Existing `organizations` detail table fields absorbed into the new first-class organization entity.
- Store world-setting generation results separately; `Project.world_*` remains the accepted active snapshot.
- Add policy gate so all old generation entrypoints obey default extraction-only behavior.
- Use `chapter_id`, `chapter_order`, optional source offsets, optional `story_time_label`, `valid_from_chapter_id`/`valid_from_chapter_order`, `valid_to_chapter_id`/`valid_to_chapter_order` for timeline semantics (both ID and order for query flexibility).
- Do not store provider reasoning summaries as canonical provenance; provenance must be source text spans, model output JSON, and review/merge audit records.
- `CharacterStateUpdateService` transition: wrap in Task 11 to route through extraction candidate pipeline, deprecate in Task 17.
- Feature flag `EXTRACTION_PIPELINE_ENABLED` (default: false) gates new extraction behavior; system falls back to legacy mode when disabled.
- Defer graph visualization, natural-language graph query, custom ontology editor, shared multi-project lore DB, fine-tuning, and full autonomous editing workflow.

## Work Objectives
### Core Objective
Make persisted novel正文 the primary source of truth for project canon: extracting candidate entities/claims from text, staging them for review/auto-merge under strict policy, and maintaining versioned relationship/profession/organization/world-setting history while preserving existing projects.

### Deliverables
- Backend test harness and golden Chinese prose fixtures.
- Character/Organization table split: new first-class `OrganizationEntity` table replacing `Character.is_organization` pattern, with backward-compatible views/queries.
- Additive SQLAlchemy models + mirrored Alembic migrations in `backend/alembic/sqlite` and `backend/alembic/postgres`.
- Extraction run/candidate/provenance/timeline/world-setting-result services and APIs.
- Data-driven provider/model capability registry, normalized reasoning setting, OpenAI Responses adapter.
- Frontend settings, candidate review, provenance, world setting result history, and timeline UI.
- Compatibility gates for old generation endpoints.
- `EXTRACTION_PIPELINE_ENABLED` feature flag for progressive rollout.

### Definition of Done (verifiable conditions with commands)
- `cd backend && python -m pytest` passes all new backend tests.
- `cd frontend && npm run build && npm run lint && npm run test -- --run` passes after frontend test infra is added.
- `docker-compose build` completes successfully.
- A fixed Chinese prose fixture creates extraction candidates with source spans, accepts/merges into canon, updates timeline projections, and preserves history.
- Ordinary users cannot AI-generate canonical characters/organizations/professions by default; advanced/admin override works and records audit metadata.
- OpenAI Responses, OpenAI Chat Completions compatibility, Claude, Gemini 2.5, Gemini 3, and unsupported reasoning combinations are covered by capability/preflight tests.

### Must Have
- Preserve existing user data.
- Add migrations to both SQLite and PostgreSQL Alembic trees for every schema change.
- Backend-enforce policy; frontend hiding alone is insufficient.
- Keep existing `/project/:projectId/*` route family stable.
- Keep routers thin; domain logic belongs under `backend/app/services`.
- Use `frontend/src/services/api.ts` and `frontend/src/types/index.ts` for shared API contracts.
- Every automatic extraction run records trigger type, source hash, status, provider/model/reasoning snapshot, source chapter/range, confidence, and evidence text.
- Failed extraction never rolls back saved/imported/generated正文.
- `EXTRACTION_PIPELINE_ENABLED` feature flag (default: false in `backend/app/config.py`) gates all new extraction triggers and candidate creation; when disabled, system operates in legacy mode.
- Character/Organization split migration must preserve all existing data via data migration step.
- Provider capability matrix must be data-driven (registry file or DB), not hardcoded; unknown models default to `auto` reasoning with logged warning.

### Must NOT Have
- No destructive migration or deletion of existing characters/orgs/careers/world settings.
- No ordinary default AI-generated canonical entity creation.
- No provider-native reasoning fields leaking into generic frontend/domain contracts.
- No silent overwrite of active world settings without accept action.
- No auto-merge of ambiguous/high-impact conflicts without explicit threshold/audit.
- No “manual visual inspection” acceptance criteria.
- No full graph visualization, ontology editor, or natural-language graph query in this plan.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: **TDD for core backend/provider/schema, tests-after for UI integration, plus build/lint/Docker smoke**.
- Backend framework to add: `pytest` with deterministic service/API tests and golden fixtures.
- Frontend framework to add: `vitest` smoke/contract tests; existing `npm run build` remains the TypeScript gate.
- QA policy: Every task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. Optimized for maximum parallelism. Wave 1 lays test + schema + provider foundations (T2 and T4 can run in parallel since both only depend on T1). Wave 2 parallelizes all core services. Task 10 is split into 10a (candidate APIs, earlier) and 10b (timeline/world APIs, later) to unblock frontend work sooner.

Wave 1: Tasks 1, 2, 4 — test harness, schema (incl. org split), provider capability registry.
Wave 2: Tasks 3, 5, 6, 8, 9, 10a — backfill, OpenAI Responses, extraction core, world results, policy gate, candidate APIs.
Wave 3: Tasks 7, 10b, 11, 12, 13, 14 — merge/timeline service, timeline/world APIs, triggers, compatibility APIs, settings UI, entity review UI.
Wave 4: Tasks 15, 16, 17, 18 — inspiration/world UI, timeline UI, cleanup/docs, integrated QA hardening.

### Dependency Matrix (full, all tasks — revised)
| Task | Blocked By | Blocks |
|---|---|---|
| 1 Test Harness | none | 2,3,4,5,6,7,8,9,10a,10b,18 |
| 2 Extraction Graph + Org Split Schema | 1 | 3,6,7,8,9,10a,10b,11,12,14,16 |
| 3 Legacy Backfill | 1,2 | 12,17 |
| 4 Provider Capability Matrix | 1 | 5,13 |
| 5 OpenAI Responses Adapter | 1,4 | 13,18 |
| 6 Extraction Core Service | 1,2 | 7,10a,11 |
| 7 Canonical Merge + Timeline Service | 1,2,6 | 10b,12,14,16 |
| 8 World Setting Result Service | 1,2 | 10b,15 |
| 9 Entity Generation Policy Gate | 1,2 | 10a,12,13,17 |
| 10a Extraction Candidate APIs | 6,9 | 11,12,14 |
| 10b Timeline + World Result APIs | 7,8 | 15,16 |
| 11 Auto + Manual Triggers | 6,10a | 18 |
| 12 Character/Org/Profession Compatibility APIs | 3,7,9,10a | 14,16,17 |
| 13 Settings/Reasoning Frontend | 4,5,9 | 14,15,18 |
| 14 Entity Review Frontend | 10a,12,13 | 16,18 |
| 15 Inspiration + World Frontend | 10b,13 | 18 |
| 16 Relationship Timeline Frontend | 7,10b,12,14 | 18 |
| 17 Cleanup + Docs | 3,9,12,14,15,16 | 18 |
| 18 Integrated QA Hardening | 1,5,11,13,14,15,16,17 | F1-F4 |

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 3 tasks → `deep` x3.
- Wave 2 → 6 tasks → `deep` x5, `unspecified-high` x1.
- Wave 3 → 6 tasks → `deep` x3, `visual-engineering` x3.
- Wave 4 → 4 tasks → `visual-engineering` x2, `writing` x1, `unspecified-high` x1.

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Add minimal test harness and golden fixtures

  **What to do**: Add backend `pytest` infrastructure and frontend `vitest` smoke infrastructure without changing product behavior. Create deterministic Chinese prose fixtures covering: two aliases for one character, one organization affiliation change, one profession change, one relationship start/change/end, one world fact, ambiguous duplicate name, and contradictory evidence. Add backend fixture validation tests and frontend smoke/type-contract tests. Add scripts only where absent: backend pytest command through requirements/config; frontend `test` script in `frontend/package.json`.
  **Must NOT do**: Do not refactor product code in this task. Do not add broad E2E/browser dependencies yet. Do not remove existing `npm run build` or `npm run lint` scripts.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: foundational test decisions affect every later task.
  - Skills: [] - no specialized skill required.
  - Omitted: [`frontend-design`] - no visual UI implementation in this task.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: [2,3,4,5,6,7,8,9,10,18] | Blocked By: []

  **References** (executor has NO interview context - be exhaustive):
  - Pattern: `frontend/package.json:1-45` - current scripts/dependency baseline; add `test` without disrupting build/lint.
  - Pattern: `backend/requirements.txt` - backend dependency baseline; add pytest dependencies here unless project has a more specific dependency file.
  - Pattern: `README.md` and `AGENTS.md` - current verification baseline says no formal tests exist.
  - Test: none existing - create first committed tests under `backend/tests/` and `frontend/src/__tests__/` or equivalent Vite/Vitest convention.

  **Acceptance Criteria** (agent-executable only):
  - [ ] `cd backend && python -m pytest tests/test_harness_smoke.py tests/test_golden_fixtures.py` exits 0.
  - [ ] `cd frontend && npm run test -- --run` exits 0.
  - [ ] `cd frontend && npm run build && npm run lint` exits 0.
  - [ ] Golden fixture files include Chinese text plus expected entity/relationship/world-fact assertions and are referenced by backend tests.

  **QA Scenarios** (MANDATORY - task incomplete without these):
  ```
  Scenario: Test harness accepts valid golden fixture
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_golden_fixtures.py -q
    Expected: exit code 0; output includes fixture cases for alias, organization affiliation, profession change, relationship timeline, and world fact
    Evidence: .sisyphus/evidence/task-1-test-harness.log

  Scenario: Fixture validator rejects malformed expected data
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_golden_fixture_validation.py -q
    Expected: exit code 0; test asserts missing source span/evidence/confidence fields raise validation errors
    Evidence: .sisyphus/evidence/task-1-test-harness-error.log
  ```

  **Commit**: YES | Message: `test: add minimal regression harness` | Files: [`backend/requirements.txt`, `backend/tests/**`, `frontend/package.json`, `frontend/vitest.config.*`, `frontend/src/**/__tests__/**`]

- [x] 2. Add extraction graph, provenance, timeline, world-result schema, and Character/Organization table split

  **What to do**: Two major schema changes in one migration set:

  **(A) Character/Organization independent table split**: Replace `Character.is_organization` pattern with a first-class `OrganizationEntity` table. Current `characters` table retains only non-organization rows. New `organization_entities` table absorbs organization-specific fields from `characters` (name, personality/特性, background, status, current_state, avatar_url, traits) plus current `organizations` detail fields (parent_org_id, level, power_level, member_count, location, motto, color). Data migration step: for each `Character` row with `is_organization=True`, create an `OrganizationEntity` row, update FKs in `organization_members`, `character_relationships` (which now becomes `entity_relationships` supporting both character and org endpoints), and `extraction_candidates`. Add `organization_type` enum column. Remove `is_organization`, `organization_type`, `organization_purpose`, `organization_members` columns from `characters` table in the same migration. Preserve all existing data.

  **(B) Extraction graph schema**: Add additive SQLAlchemy models and mirrored Alembic migrations for: `ExtractionRun`, `ExtractionCandidate`, `EntityAlias`, `EntityProvenance`, `RelationshipTimelineEvent`, `WorldSettingResult`, and audit fields. `ExtractionCandidate.canonical_target_type` uses enum `character | organization | career` (three distinct types, no ambiguity). Required fields include project/user scope, trigger type, source hash, status, provider/model/reasoning snapshot, source chapter/range, source offsets, evidence text, confidence, candidate status, canonical target type/id, `valid_from_chapter_id`/`valid_from_chapter_order`, `valid_to_chapter_id`/`valid_to_chapter_order`, optional `story_time_label`, created/reviewed/accepted timestamps, and rollback/supersession IDs. Add indexes for project/status, run/project, source hash, canonical target, chapter timeline, and normalized alias.

  **(C) Settings fields for reasoning/policy**: Add columns to `settings` table: `default_reasoning_intensity` (String(20), default 'auto'), `reasoning_overrides` (Text, nullable — JSON per-provider/model), `allow_ai_entity_generation` (Boolean, default False). Add `EXTRACTION_PIPELINE_ENABLED` to `backend/app/config.py` as env-driven setting (default False).

  **Must NOT do**: Do not delete existing data rows. Do not replace `Project.world_*`; keep it as active snapshot. Do not create migrations in only one Alembic tree. Do not drop `characters` rows for organizations before creating corresponding `organization_entities` rows.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: schema is high-impact and must preserve data.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - backend persistence only.

  **Parallelization**: Can Parallel: YES (with Task 4) | Wave 1 | Blocks: [3,6,7,8,9,10a,10b,11,12,14,16] | Blocked By: [1]

  **References**:
  - Pattern: `backend/app/models/project.py:8-55` - current world setting active snapshot fields.
  - Pattern: `backend/app/models/character.py:8-57` - character/organization-related existing model surface; `is_organization` field to split.
  - Pattern: `backend/app/models/relationship.py:8-116` - current relationship/org/member persistence; `Organization` detail table to absorb.
  - Pattern: `backend/app/models/career.py:8-77` - current career/profession persistence.
  - Pattern: `backend/app/models/settings.py:8-53` - settings table for new reasoning/policy columns.
  - Pattern: `backend/alembic/sqlite/**` and `backend/alembic/postgres/**` - dual migration trees must stay aligned.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_migrations.py tests/test_schema_contracts.py` exits 0.
  - [ ] Both `backend/alembic/sqlite/versions/*extraction*` and `backend/alembic/postgres/versions/*extraction*` exist and define equivalent schema changes.
  - [ ] Tests assert all new tables/columns/indexes exist and existing project/character/career/world fields remain.
  - [ ] Tests assert `organization_entities` table exists with all migrated org data and old `characters.is_organization=True` rows are removed.
  - [ ] Tests assert `settings` table has `default_reasoning_intensity`, `reasoning_overrides`, `allow_ai_entity_generation` columns.
  - [ ] `EXTRACTION_PIPELINE_ENABLED` config setting exists and defaults to False.
  - [ ] Reverting/down migration behavior is defined where repo migration style supports downgrade.

  **QA Scenarios**:
  ```
  Scenario: Fresh database migrates to extraction graph schema with org split
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_migrations.py::test_fresh_database_has_extraction_graph_schema -q
    Expected: exit code 0; tables extraction_runs, extraction_candidates, entity_aliases, entity_provenance, relationship_timeline_events, world_setting_results, organization_entities are detected; characters table has no is_organization column
    Evidence: .sisyphus/evidence/task-2-schema.log

  Scenario: Org data migration preserves all existing organizations
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_migrations.py::test_org_split_migration_preserves_data -q
    Expected: exit code 0; all former is_organization=True characters exist as organization_entities with matching fields; FK references updated
    Evidence: .sisyphus/evidence/task-2-org-split.log

  Scenario: Migration parity fails if one Alembic tree is missing a table
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_migration_parity.py -q
    Expected: exit code 0; test compares SQLite/PostgreSQL migration declarations and would fail on missing/mismatched schema names
    Evidence: .sisyphus/evidence/task-2-schema-parity.log
  ```

  **Commit**: YES | Message: `db: add extraction schema and split character/organization tables` | Files: [`backend/app/models/**`, `backend/app/config.py`, `backend/alembic/sqlite/**`, `backend/alembic/postgres/**`, `backend/tests/test_migrations.py`, `backend/tests/test_schema_contracts.py`]

- [x] 3. Backfill legacy records into provenance-compatible canon

  **What to do**: Add an idempotent backfill service and migration/test path that marks existing characters, organizations, careers/professions, relationships, and `Project.world_*` values as accepted legacy/manual canon. Create provenance rows with source type `legacy_existing_record`, confidence `1.0` only for user-authored/manual existing records when no better provenance exists, and `source_chapter_id = null`. Create aliases from existing display/name/title fields. Create initial timeline events for existing relationship/career/org affiliation data with `valid_from_chapter_id = null` and `valid_to_chapter_id = null` so current projections include legacy data.
  **Must NOT do**: Do not infer new entities during migration. Do not call AI in migration/backfill. Do not overwrite user-edited fields. Do not hard-delete duplicates.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: data preservation and idempotency are critical.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - no frontend UI design work here.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [12,17] | Blocked By: [1,2]

  **References**:
  - Pattern: `backend/app/models/character.py:8-57` - existing character/org data to preserve.
  - Pattern: `backend/app/models/relationship.py:8-116` - existing relationship/org/member data to preserve.
  - Pattern: `backend/app/models/career.py:8-77` - existing career/profession data to preserve.
  - Pattern: `backend/app/models/project.py:8-55` - existing world settings to preserve as active snapshot.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_legacy_backfill.py` exits 0.
  - [ ] Tests create legacy project data, run backfill twice, and assert no duplicate provenance, aliases, world results, or timeline events.
  - [ ] Tests assert all original records remain editable and queryable through existing APIs.
  - [ ] Backfill creates no extraction runs and performs no AI/network calls.

  **QA Scenarios**:
  ```
  Scenario: Legacy project survives backfill
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_legacy_backfill.py::test_legacy_records_preserved_and_provenance_created -q
    Expected: exit code 0; original records unchanged; provenance/timeline/world-result rows created with legacy_existing_record source
    Evidence: .sisyphus/evidence/task-3-backfill.log

  Scenario: Backfill is idempotent
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_legacy_backfill.py::test_backfill_can_run_twice_without_duplicates -q
    Expected: exit code 0; row counts remain stable after second backfill
    Evidence: .sisyphus/evidence/task-3-backfill-error.log
  ```

  **Commit**: YES | Message: `db: backfill legacy canon provenance` | Files: [`backend/app/services/*backfill*`, `backend/tests/test_legacy_backfill.py`, `backend/alembic/sqlite/**`, `backend/alembic/postgres/**`]

- [x] 4. Add data-driven provider/model capability registry and normalized reasoning settings contract

  **What to do**: Add a **data-driven** backend capability registry for provider/model reasoning support. The registry must be a loadable JSON/YAML file or database-backed table (not hardcoded conditionals), each entry containing: provider, model pattern (glob or regex), supported intensity levels, default intensity, provider-native field mappings, `last_verified_date`, and notes. Add a normalized internal intensity enum: `auto | off | low | medium | high | maximum`.

  **BaseAIProvider interface change**: Add `reasoning_config: Optional[NormalizedReasoningConfig] = None` parameter to `BaseAIProvider.generate()` and `generate_stream()`. `NormalizedReasoningConfig` is a dataclass with fields: `intensity: ReasoningIntensity`, `provider_payload: Dict[str, Any]` (populated by preflight from registry). Each provider implementation maps the normalized config to its native fields.

  **Unknown model fallback**: When a model is not found in the registry, default to `auto` reasoning (let provider decide) and log a warning — do NOT reject the request.

  Settings schema fields (`default_reasoning_intensity`, `reasoning_overrides`, `allow_ai_entity_generation`) are created by Task 2 migration; this task reads and validates them.

  Implement preflight validation that returns deterministic errors before any HTTP call when a selected intensity is unsupported. Capability defaults:
  - OpenAI Responses: `auto` omits effort; `off` maps to `none` only when model supports `none`; `low|medium|high` map directly where supported; `maximum` maps to the highest supported effort.
  - Claude: `auto` uses provider default; `off` maps to `thinking.type=disabled` only where supported; `low|medium|high` map to `output_config.effort`; `maximum` maps to highest supported level per model.
  - Gemini 3: `low|medium|high` map to `thinkingConfig.thinkingLevel`; `off` only where model supports disabling; `maximum` maps to highest supported level.
  - Gemini 2.5: `thinkingConfig.thinkingBudget`; use per-model budget ranges from research.
  **Must NOT do**: Do not expose provider-native fields directly as primary frontend state. Do not silently downgrade explicit unsupported user selections; fail preflight unless setting is `auto`. Do not hardcode model names in conditional branches; use registry lookups.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: cross-provider compatibility matrix and validation logic are high-risk.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - no UI styling in this task.

  **Parallelization**: Can Parallel: YES (with Task 2) | Wave 1 | Blocks: [5,13] | Blocked By: [1]

  **References**:
  - Pattern: `backend/app/api/settings.py:102-160,163-250,452-544,571-691,803-871,989-1297` - existing settings/model fetch/preset/provider checks.
  - Pattern: `backend/app/models/settings.py:8-53` - persisted AI/provider/MCP settings (new columns from Task 2).
  - Pattern: `backend/app/schemas/settings.py:7-143` - settings/preset API contracts.
  - Pattern: `backend/app/services/ai_providers/base_provider.py:6-36` - BaseAIProvider interface to extend with `reasoning_config` param.
  - External: `https://developers.openai.com/api/docs/guides/reasoning` - OpenAI reasoning effort.
  - External: `https://docs.anthropic.com/en/docs/build-with-claude/effort` - Claude effort support.
  - External: `https://ai.google.dev/gemini-api/docs/thinking` - Gemini thinking config.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_ai_provider_capabilities.py` exits 0.
  - [ ] Capability registry file exists and is loadable; tests cover known and unknown model lookups.
  - [ ] Tests cover supported and unsupported combinations for representative OpenAI, Claude, Gemini models.
  - [ ] `BaseAIProvider.generate()` and `generate_stream()` accept `reasoning_config` parameter.
  - [ ] Settings schemas expose normalized enum and capability metadata, not raw provider fields.
  - [ ] Unsupported explicit settings fail before network calls; `auto` and unknown models pass without error.

  **QA Scenarios**:
  ```
  Scenario: Supported reasoning setting maps to provider payload
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_ai_provider_capabilities.py::test_supported_reasoning_mappings -q
    Expected: exit code 0; OpenAI medium, Claude high, Gemini 3 high, Gemini 2.5 medium budget produce valid payload fragments
    Evidence: .sisyphus/evidence/task-4-provider-capabilities.log

  Scenario: Unsupported reasoning setting fails preflight
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_ai_provider_capabilities.py::test_unsupported_reasoning_fails_before_http -q
    Expected: exit code 0; mocked HTTP client is not called and deterministic validation error is returned
    Evidence: .sisyphus/evidence/task-4-provider-capabilities-preflight.log

  Scenario: Unknown model defaults to auto reasoning
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_ai_provider_capabilities.py::test_unknown_model_defaults_to_auto -q
    Expected: exit code 0; unknown model name returns auto with warning log; no rejection
    Evidence: .sisyphus/evidence/task-4-provider-capabilities-fallback.log
  ```

  **Commit**: YES | Message: `ai: add data-driven provider reasoning capability registry` | Files: [`backend/app/services/**capabilit*`, `backend/app/services/ai_providers/base_provider.py`, `backend/app/schemas/settings.py`, `backend/app/api/settings.py`, `backend/tests/test_ai_provider_capabilities.py`, `backend/data/reasoning_capabilities.json`]

- [x] 5. Add OpenAI Responses API adapter while preserving Chat Completions compatibility

  **What to do**: Add OpenAI Responses API support using the following **explicit architecture**:

  **(A) Client layer** (`OpenAIClient`): Add `create_response()` and `create_response_stream()` methods alongside existing `chat_completion()` and `chat_completion_stream()`. Both APIs share the same HTTP client pool, API key, and base URL — do NOT create a separate client class. The `/responses` endpoint uses input items (not messages), output items (not choices), and has different streaming event types (`response.output_item.added`, `response.content_part.delta`, etc.).

  **(B) Provider layer** (`OpenAIProvider`): In `generate()` and `generate_stream()`, use the Task 4 capability registry to decide which client method to call. When `reasoning_config` is present and the model supports Responses API, use `create_response()`; otherwise fall back to `chat_completion()`. Normalize both paths into one internal result shape: text, structured JSON payload, tool/function-call events, usage, finish status, provider metadata, and reasoning continuation metadata (`previous_response_id` or reasoning item pass-through).

  **(C) Service layer** (`AIService`): No changes to public interface; provider routing is transparent.

  **Must NOT do**: Do not call `/responses` directly from routers or frontend. Do not create a separate `OpenAIResponsesClient` class. Do not break current streaming/tool-call behavior. Do not store reasoning summaries as canonical extraction provenance.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: provider abstractions, streaming, and tool-calls are fragile.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - backend provider work only.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [13,18] | Blocked By: [1,4]

  **References**:
  - Pattern: `backend/app/services/ai_clients/openai_client.py:11-87,89-175` - current `/chat/completions` implementation; add `create_response()` here.
  - Pattern: `backend/app/services/ai_providers/openai_provider.py:11-110,129-174` - current OpenAI provider; add routing logic here.
  - Pattern: `backend/app/services/ai_providers/base_provider.py:6-36` - base interface with new `reasoning_config` param from Task 4.
  - Pattern: `backend/app/services/ai_service.py:30-165,197-260,331-345` - provider normalization; no public API change needed.
  - External: `https://developers.openai.com/api/docs/api-reference/responses/create` - Responses create API.
  - External: `https://developers.openai.com/api/docs/api-reference/responses/object` - Responses object/reasoning metadata.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_openai_responses_adapter.py tests/test_ai_service_openai_compat.py` exits 0.
  - [ ] `OpenAIClient` has both `chat_completion*` and `create_response*` methods; no separate client class exists.
  - [ ] Tests assert `/responses` payload contains reasoning fields only after capability preflight.
  - [ ] Tests assert legacy `/chat/completions` path still works for existing settings.
  - [ ] Tests assert streaming/tool-call normalization preserves existing event contract expected by callers.

  **QA Scenarios**:
  ```
  Scenario: OpenAI Responses adapter normalizes text and tool calls
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_openai_responses_adapter.py::test_responses_adapter_normalizes_output_and_tool_calls -q
    Expected: exit code 0; normalized result includes text/tool events/usage/provider metadata and no frontend-specific fields
    Evidence: .sisyphus/evidence/task-5-openai-responses.log

  Scenario: Legacy chat completions remains compatible
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_ai_service_openai_compat.py::test_chat_completions_path_still_works -q
    Expected: exit code 0; mocked `/chat/completions` request shape matches pre-refactor expectations
    Evidence: .sisyphus/evidence/task-5-openai-compat.log
  ```

  **Commit**: YES | Message: `ai: add OpenAI Responses adapter` | Files: [`backend/app/services/ai_clients/openai_client.py`, `backend/app/services/ai_providers/openai_provider.py`, `backend/tests/test_openai_responses_adapter.py`, `backend/tests/test_ai_service_openai_compat.py`]

- [x] 6. Implement extraction core service and structured prompt schema

  **What to do**: Add `backend/app/services/extraction_service.py` (or equivalent service module following repo style) that reads persisted chapter text and creates extraction runs/candidates. Use a structured output schema for candidate types: `character`, `organization`, `profession`, `relationship`, `organization_affiliation`, `profession_assignment`, `world_fact`, `character_state`. Each candidate must include normalized name(s), aliases, confidence, evidence text, source `chapter_id`, `chapter_order`, `source_start_offset`, `source_end_offset`, optional `story_time_label`, raw model payload, and status `pending`. Add content hash dedupe: same chapter text + extraction schema version + prompt version + project ID returns existing completed run unless `force=true`. Use prompt contracts in `prompt_service.py` or a new prompt module consistent with existing prompt registry.
  **Must NOT do**: Do not promote candidates to canonical entities in this service. Do not run extraction on unsaved editor content. Do not roll back chapter text if extraction fails.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: core domain service and structured AI output validation.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - backend service only.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [7,10,11] | Blocked By: [1,2]

  **References**:
  - Pattern: `backend/app/services/book_import_service.py:644-703,705-718,909-995,1010-1159,1500-1759` - existing import reverse extraction behavior to consolidate.
  - Pattern: `backend/app/services/prompt_service.py:2851-2969,3300-3525` - existing reverse extraction prompts/schema contracts.
  - Pattern: `backend/app/services/character_state_update_service.py:1-260` - existing chapter analysis/state update behavior to replace with candidate staging.
  - API/Type: new models from Task 2 - extraction runs/candidates/provenance schema.
  - Test: `backend/tests/fixtures/**` from Task 1 - golden Chinese prose.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_extraction_pipeline.py` exits 0.
  - [ ] Golden prose creates one extraction run and pending candidates with exact source offsets/evidence snippets.
  - [ ] Re-running extraction on unchanged text without `force=true` does not duplicate candidates.
  - [ ] Malformed model JSON is recorded as failed extraction run with error details and no canonical mutation.

  **QA Scenarios**:
  ```
  Scenario: Persisted chapter text creates staged candidates
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_extraction_pipeline.py::test_chinese_prose_creates_candidates_with_provenance -q
    Expected: exit code 0; candidates include character, organization, profession, relationship, affiliation, profession assignment, world fact with source spans
    Evidence: .sisyphus/evidence/task-6-extraction-core.log

  Scenario: Malformed AI output fails safely
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_extraction_pipeline.py::test_malformed_model_output_marks_run_failed_without_canonical_mutation -q
    Expected: exit code 0; extraction run status failed; no canonical entity/timeline/world-result rows created
    Evidence: .sisyphus/evidence/task-6-extraction-core-error.log
  ```

  **Commit**: YES | Message: `service: add extraction run orchestration` | Files: [`backend/app/services/extraction_service.py`, `backend/app/services/prompt_service.py`, `backend/tests/test_extraction_pipeline.py`, `backend/tests/fixtures/**`]

- [x] 7. Implement canonical merge, dedupe, rollback, and timeline projection service

  **What to do**: Add a service that converts pending extraction candidates into canonical records only through explicit accept/merge, deterministic safe auto-merge, or advanced/admin override. Rules: auto-merge is allowed only when confidence `>= 0.92`, normalized name/alias matches one existing canonical entity, candidate type matches target type, and no conflicting active timeline claim exists; otherwise candidate remains pending review. Add accept/reject/merge/supersede/rollback operations. Maintain aliases and entity provenance per accepted claim. For relationships/professions/org affiliations, create append-only `RelationshipTimelineEvent` rows with valid chapter ranges and derive current projection by querying the latest non-ended event for a target chapter/order. Rollback must supersede events/provenance rather than hard-delete rows.
  **Must NOT do**: Do not auto-merge ambiguous names, contradictory relationships, or cross-type matches. Do not hard-delete provenance/timeline rows referenced by accepted canon. Do not mutate world settings here; Task 8 owns world-setting results.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: canon integrity and temporal state transitions are complex.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - no frontend UI work in this task.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [10b,12,14,16] | Blocked By: [1,2,6]

  **References**:
  - Pattern: `backend/app/models/relationship.py:8-116` - current relationship/org/member persistence to project from timeline.
  - Pattern: `backend/app/models/character.py:8-57` - canonical character/org targets.
  - Pattern: `backend/app/models/career.py:8-77` - profession/career targets.
  - Pattern: `backend/app/services/character_state_update_service.py:1-830` - entire service to absorb: psychological state updates (L270-314), relationship intimacy adjustments (L316-456), organization membership cascades (L458-648), organization state updates (L650-830), survival status cascades (L188-268). All logic must be replicated as append-only timeline events rather than direct field overwrites.
  - Pattern: `backend/app/services/auto_character_service.py` and `auto_organization_service.py` - auto-creation services to be routed through policy gate (Task 9) and candidate pipeline.
  - Test: `backend/tests/fixtures/**` - timeline/alias/contradiction cases.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_candidate_merge.py tests/test_relationship_timeline.py` exits 0.
  - [ ] Accept/merge/reject/rollback operations are idempotent and audited.
  - [ ] Querying chapter 3 vs chapter 6 vs chapter 10 returns correct relationship/profession/org affiliation state from timeline events.
  - [ ] Ambiguous alias/duplicate/conflict cases remain pending and create no canonical mutation.

  **QA Scenarios**:
  ```
  Scenario: Candidate acceptance creates canon, provenance, and timeline projection
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_candidate_merge.py::test_accept_candidate_creates_canon_provenance_and_projection -q
    Expected: exit code 0; canonical entity linked to provenance; timeline query returns accepted relationship/profession/org affiliation
    Evidence: .sisyphus/evidence/task-7-merge-timeline.log

  Scenario: Ambiguous candidate is not auto-merged
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_candidate_merge.py::test_ambiguous_alias_does_not_auto_merge -q
    Expected: exit code 0; candidate remains pending; no new canonical entity, alias, or timeline event is created
    Evidence: .sisyphus/evidence/task-7-merge-timeline-error.log
  ```

  **Commit**: YES | Message: `service: add canonical candidate merge flow` | Files: [`backend/app/services/*merge*`, `backend/app/services/*timeline*`, `backend/tests/test_candidate_merge.py`, `backend/tests/test_relationship_timeline.py`]

- [x] 8. Version world-setting generation results and active snapshot acceptance

  **What to do**: Refactor world-setting generation so model output creates `WorldSettingResult` rows first. Each result stores project ID, source extraction run/candidates if any, provider/model/reasoning snapshot, prompt/template version, generated fields matching current `Project.world_*`, raw payload, status `pending|accepted|rejected|superseded`, and accept/reject/rollback audit fields. Accepting a result updates the active `Project.world_*` snapshot. Rollback restores the previous accepted snapshot by marking the current result superseded and re-applying the previous accepted result. Existing world settings become an initial accepted legacy result via Task 3 backfill.
  **Must NOT do**: Do not overwrite `Project.world_*` during generation. Do not delete prior world-setting versions. Do not mix inspiration ideas into active world settings without accept/apply action.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: preserves world-setting data while changing generation semantics.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - backend service/API preparation only.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [10b,15] | Blocked By: [1,2]

  **References**:
  - Pattern: `backend/app/models/project.py:8-55` - active world setting fields to preserve.
  - Pattern: `backend/app/api/wizard_stream.py:1551-1639` - existing world regeneration flow.
  - Pattern: `frontend/src/pages/WorldSetting.tsx:12-119,128-246` - current display/edit/regenerate behavior to support later UI.
  - Pattern: `backend/app/schemas/project.py:14-63` - project/world-setting API contracts.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_world_setting_results.py` exits 0.
  - [ ] Generation creates a pending world-setting result and leaves `Project.world_*` unchanged.
  - [ ] Accept updates active snapshot and records provenance/audit metadata.
  - [ ] Rollback restores prior accepted snapshot without deleting result history.

  **QA Scenarios**:
  ```
  Scenario: World generation creates pending version only
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_world_setting_results.py::test_generation_creates_pending_result_without_overwrite -q
    Expected: exit code 0; pending result exists; project active world fields equal pre-generation values
    Evidence: .sisyphus/evidence/task-8-world-results.log

  Scenario: Rollback restores previous accepted world setting
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_world_setting_results.py::test_rollback_restores_previous_accepted_snapshot -q
    Expected: exit code 0; active snapshot equals previous accepted result; all result rows remain queryable
    Evidence: .sisyphus/evidence/task-8-world-results-error.log
  ```

  **Commit**: YES | Message: `service: version world setting generation results` | Files: [`backend/app/services/*world*`, `backend/app/api/wizard_stream.py`, `backend/app/schemas/project.py`, `backend/tests/test_world_setting_results.py`]

- [x] 9. Add backend-enforced entity generation policy gate and advanced override audit

  **What to do**: Add a central policy service used by all character/organization/profession AI generation entrypoints. Default behavior for ordinary users: AI generation may create extraction candidates/drafts only, never canonical `Character`/organization/`Career` records. Add backend setting `allow_ai_entity_generation` default `false`, plus request-time permission check: advanced/admin override requires either admin user (`request.state.is_admin` or existing equivalent) or explicit advanced setting accepted by backend policy. Every override action records actor, project, endpoint/source, generated entity type, provider/model, reason, timestamp, and resulting canonical IDs. Manual create/edit endpoints remain allowed and must not require AI override.
  **Must NOT do**: Do not implement this as frontend-only hiding. Do not block manual corrections. Do not allow old SSE endpoints to bypass the policy.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: cross-cutting security/product policy.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - UI switch comes later in Task 13.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [10a,12,13,17] | Blocked By: [1,2]

  **References**:
  - Pattern: `backend/app/api/characters.py:34-194,197-260` - character list/generation entrypoints.
  - Pattern: `backend/app/api/organizations.py:36-214,218-260` - organization CRUD/generation stream.
  - Pattern: `backend/app/api/careers.py:36-260` - career CRUD/generation stream.
  - Pattern: `backend/app/api/wizard_stream.py:1380-1520` - wizard post-processing that creates characters/orgs.
  - Pattern: `backend/app/api/outlines.py:720-981,984-1039` - outline generation and auto-create missing entities.
  - Pattern: `backend/app/services/auto_character_service.py:17-260,549-557` and `auto_organization_service.py:17-260,457-465` - existing auto creation services.
  - Pattern: `backend/app/middleware/auth_middleware.py` - backend user/admin state source per project knowledge base.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_entity_generation_policy.py` exits 0.
  - [ ] Ordinary user AI-generation attempts return policy response/candidate-only behavior and create no canonical entity.
  - [ ] Admin/advanced override allows generation and writes audit metadata.
  - [ ] Manual create/edit endpoints still succeed without override.
  - [ ] All known generation call sites use the central policy service.

  **QA Scenarios**:
  ```
  Scenario: Ordinary AI entity generation is blocked from canonical creation
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_entity_generation_policy.py::test_ordinary_user_ai_generation_creates_no_canonical_entity -q
    Expected: exit code 0; response indicates disabled/candidate-only policy; canonical row count unchanged
    Evidence: .sisyphus/evidence/task-9-policy-gate.log

  Scenario: Advanced/admin override is audited
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_entity_generation_policy.py::test_admin_override_generates_and_records_audit -q
    Expected: exit code 0; canonical entity created only with override; audit row includes actor/source/reason/model/result IDs
    Evidence: .sisyphus/evidence/task-9-policy-gate-error.log
  ```

  **Commit**: YES | Message: `policy: gate AI entity generation by advanced setting` | Files: [`backend/app/services/*policy*`, `backend/app/api/characters.py`, `backend/app/api/organizations.py`, `backend/app/api/careers.py`, `backend/app/api/wizard_stream.py`, `backend/app/api/outlines.py`, `backend/tests/test_entity_generation_policy.py`]

- [x] 10a. Expose extraction candidate and review APIs

  **What to do**: Add thin FastAPI routers/schemas for extraction run and candidate management. Required endpoints under existing `/api` convention: list/get extraction runs; list candidates with filters (`status`, `type`, `chapter_id`, `run_id`, `canonical_target`); accept/reject/merge candidate; rollback merge. Include deterministic status values: `pending`, `running`, `completed`, `failed`, `cancelled` for runs and `pending`, `accepted`, `rejected`, `merged`, `superseded` for candidates. Register new router(s) in `backend/app/main.py`.
  **Must NOT do**: Do not put merge/extraction business logic in router functions. Do not break existing route prefixes.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: API contracts define the frontend/backend boundary.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - backend API only.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: [11,12,14] | Blocked By: [6,9]

  **References**:
  - Pattern: `backend/app/main.py:130-161` - router registration style.
  - Pattern: `backend/app/api/characters.py:34-260`, `organizations.py:36-260` - current router conventions.
  - Pattern: `backend/app/schemas/character.py:7-123` - schema style.
  - API/Type: services from Tasks 6, 9 - extraction core, policy gate.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_extraction_api.py` exits 0.
  - [ ] API tests assert router registration under `/api` and stable JSON response schemas.
  - [ ] API tests assert failed merge operations return structured errors and do not mutate canon.
  - [ ] OpenAPI schema generation succeeds without import errors.

  **QA Scenarios**:
  ```
  Scenario: Candidate review API accepts candidate
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_extraction_api.py::test_accept_candidate_api -q
    Expected: exit code 0; POST accept returns accepted candidate with provenance
    Evidence: .sisyphus/evidence/task-10a-extraction-api.log

  Scenario: Invalid merge target returns structured error without mutation
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_extraction_api.py::test_invalid_merge_target_returns_error_without_mutation -q
    Expected: exit code 0; HTTP 4xx response includes code/message; canonical row counts unchanged
    Evidence: .sisyphus/evidence/task-10a-extraction-api-edge.log
  ```

  **Commit**: YES | Message: `api: expose extraction candidate review endpoints` | Files: [`backend/app/api/*extraction*`, `backend/app/schemas/**`, `backend/app/main.py`, `backend/tests/test_extraction_api.py`]

- [x] 10b. Expose timeline query and world-setting result APIs

  **What to do**: Add thin FastAPI routers/schemas for timeline and world-setting result queries. Required endpoints: list/query timeline relationships by project and optional chapter/order; list/get/accept/reject/rollback world-setting results. Register router(s) in `backend/app/main.py`.
  **Must NOT do**: Do not put timeline projection or world-setting business logic in router functions.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: API contracts for temporal queries.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - backend API only.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [15,16] | Blocked By: [7,8]

  **References**:
  - Pattern: `backend/app/main.py:130-161` - router registration style.
  - Pattern: `backend/app/schemas/project.py:14-63` - project/world-setting API contracts.
  - API/Type: services from Tasks 7, 8 - merge/timeline, world results.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_timeline_api.py tests/test_world_setting_results_api.py` exits 0.
  - [ ] Timeline query returns correct relationship/profession/org state for specified chapter.
  - [ ] World-setting result accept/rollback APIs work correctly.
  - [ ] OpenAPI schema generation succeeds without import errors.

  **QA Scenarios**:
  ```
  Scenario: Timeline API returns correct state for specified chapter
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_timeline_api.py::test_timeline_query_by_chapter -q
    Expected: exit code 0; GET timeline returns expected relationship state for queried chapter
    Evidence: .sisyphus/evidence/task-10b-timeline-api.log

  Scenario: World-setting result accept updates active snapshot
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_world_setting_results_api.py::test_accept_world_result_updates_snapshot -q
    Expected: exit code 0; POST accept updates Project.world_* and returns accepted result
    Evidence: .sisyphus/evidence/task-10b-world-api.log
  ```

  **Commit**: YES | Message: `api: expose timeline and world-setting result endpoints` | Files: [`backend/app/api/*timeline*`, `backend/app/api/*world*`, `backend/app/schemas/**`, `backend/app/main.py`, `backend/tests/test_timeline_api.py`, `backend/tests/test_world_setting_results_api.py`]

- [x] 11. Integrate automatic and manual extraction triggers

  **What to do**: Hook extraction after persisted chapter save/update, after generated chapter content is successfully persisted, and after TXT import apply completes. All triggers must check `EXTRACTION_PIPELINE_ENABLED` feature flag and skip extraction when disabled.

  **CharacterStateUpdateService wrapping**: In this task, wrap `CharacterStateUpdateService` so that when `EXTRACTION_PIPELINE_ENABLED=True`, its methods create extraction candidates instead of directly mutating `Character.current_state`, `CharacterRelationship.intimacy_level`, or `OrganizationMember` fields. Specifically:
  - `_update_psychological_state()` → creates a `character_state` extraction candidate
  - `_update_relationships()` → creates `relationship` extraction candidates
  - `_update_organization_memberships()` → creates `organization_affiliation` extraction candidates
  - `_update_survival_status()` → creates `character_state` candidate with high confidence + auto-accept flag
  When `EXTRACTION_PIPELINE_ENABLED=False`, the original direct-mutation behavior is preserved unchanged.

  Add manual re-extract endpoints/actions for project-wide, chapter-level, and chapter-range modes. Trigger behavior: automatic extraction creates a run only after text persistence succeeds; failed extraction marks run failed and never rolls back saved text/import/generation; repeated saves with unchanged content reuse source hash and do not duplicate candidates; regenerated/replaced chapter content supersedes prior evidence for that chapter.
  **Must NOT do**: Do not run extraction on every keystroke or unsaved editor state. Do not block the save/import/generation response on long AI extraction when an async/status path exists. Do not delete canonicals automatically during re-extract.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: cross-cutting trigger integration with persistence flows.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - frontend trigger controls are later tasks.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: [18] | Blocked By: [6,10a]

  **References**:
  - Pattern: `backend/app/api/book_import.py:30-84,133-207,210-282` - import task/apply/retry SSE workflow.
  - Pattern: `backend/app/services/book_import_service.py:644-703,705-718,909-995,1010-1159,1500-1759` - current import extraction and cleanup behavior.
  - Pattern: `backend/app/api/wizard_stream.py:41-231,1380-1520` - generation persistence/wizard flow.
  - Pattern: `backend/app/api/outlines.py:58-158,720-981` - outline/chapter-adjacent generation flows to inspect for persistence hooks.
  - API/Type: Task 10 extraction run API/status model.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_extraction_triggers.py` exits 0.
  - [ ] Chapter save, chapter generation, and TXT import tests each create exactly one run for changed content.
  - [ ] Unchanged content does not duplicate runs/candidates.
  - [ ] Extraction failure after save/import/generation preserves persisted text and exposes failed run status.
  - [ ] Manual project/chapter/range re-extract creates new runs without deleting canonicals.

  **QA Scenarios**:
  ```
  Scenario: Import completion triggers extraction without blocking imported text
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_extraction_triggers.py::test_import_apply_triggers_extraction_after_text_persisted -q
    Expected: exit code 0; imported chapters exist; extraction run created with trigger_type book_import; candidates staged
    Evidence: .sisyphus/evidence/task-11-triggers.log

  Scenario: Failed post-save extraction preserves chapter text
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_extraction_triggers.py::test_failed_extraction_does_not_rollback_saved_chapter -q
    Expected: exit code 0; chapter content remains; extraction run status failed with error; no canonical mutation
    Evidence: .sisyphus/evidence/task-11-triggers-error.log
  ```

  **Commit**: YES | Message: `service: trigger extraction after text persistence` | Files: [`backend/app/api/book_import.py`, `backend/app/services/book_import_service.py`, `backend/app/api/wizard_stream.py`, `backend/app/api/outlines.py`, `backend/app/services/extraction_service.py`, `backend/tests/test_extraction_triggers.py`]

- [x] 12. Refactor character, organization, and profession APIs for extraction-first compatibility

  **What to do**: Update existing character/organization/career endpoints so current CRUD/list/edit behavior remains compatible while new response shapes can include provenance, aliases, candidate counts, timeline summaries, and generation policy status. Ordinary AI generation endpoints must return candidate-only/policy responses unless advanced/admin override is active. Careers must be treated as the canonical profession taxonomy for Phase 1; profession assignments are timeline relationships from characters to careers. Existing UI routes must continue receiving enough current-state data to render before frontend refactor lands.
  **Must NOT do**: Do not rename existing route paths casually. Do not remove manual create/edit. Do not expose timeline internals as required fields for old clients unless backward-compatible/defaulted.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: compatibility layer across three core domains.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - frontend consumes this in later tasks.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [14,16,17] | Blocked By: [3,7,9,10a]

  **References**:
  - Pattern: `backend/app/api/characters.py:34-194,197-260` - character API/list/generation surface.
  - Pattern: `backend/app/api/organizations.py:36-214,218-260` - organization/member management surface.
  - Pattern: `backend/app/api/careers.py:36-260` - career/profession surface.
  - API/Type: `backend/app/schemas/character.py:7-123` - current response contracts.
  - API/Type: `backend/app/models/career.py:8-77` - careers as profession taxonomy.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_entity_api_compatibility.py tests/test_profession_timeline_api.py` exits 0.
  - [ ] Existing list/get/create/edit/delete tests for characters/orgs/careers still pass.
  - [ ] New responses include provenance/timeline summaries when requested via explicit query flag, without breaking default old shape.
  - [ ] Profession assignment timeline queries return chapter-specific occupation state.
  - [ ] AI generation endpoint policy behavior is consistent across character/org/career.

  **QA Scenarios**:
  ```
  Scenario: Existing entity APIs remain backward compatible
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_entity_api_compatibility.py::test_existing_entity_crud_contracts_still_work -q
    Expected: exit code 0; old response fields remain; manual create/edit still succeeds
    Evidence: .sisyphus/evidence/task-12-entity-api.log

  Scenario: Profession timeline query changes by chapter
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_profession_timeline_api.py::test_profession_assignment_changes_across_chapters -q
    Expected: exit code 0; chapter 3 returns old profession; chapter 8 returns new profession; history remains queryable
    Evidence: .sisyphus/evidence/task-12-entity-api-error.log
  ```

  **Commit**: YES | Message: `api: keep entity APIs compatible with extraction canon` | Files: [`backend/app/api/characters.py`, `backend/app/api/organizations.py`, `backend/app/api/careers.py`, `backend/app/schemas/character.py`, `backend/tests/test_entity_api_compatibility.py`, `backend/tests/test_profession_timeline_api.py`]

- [x] 13. Add frontend settings for reasoning capabilities and advanced entity-generation override

  **What to do**: Update shared frontend types/API wrappers and Settings UI for normalized reasoning intensity. Display provider/model capability metadata from backend and disable unsupported intensity options instead of allowing invalid submissions. Add backend-backed advanced/admin setting for `allow_ai_entity_generation`, default off, with warning copy: “默认从正文自动提取角色/组织/职业；开启后才允许 AI 直接生成入库”. Settings save/test must call backend preflight and surface deterministic validation messages for unsupported OpenAI/Claude/Gemini combinations. Preserve current model fetch/API test/preset/MCP behaviors.
  **Must NOT do**: Do not hardcode provider-native reasoning fields as primary UI state. Do not make advanced override frontend-only. Do not break current Settings page model fetch/preset flows.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: user-facing settings UI plus typed API integration.
  - Skills: [`frontend-design`] - needed for clean, non-confusing settings UX.
  - Omitted: [`ui-ux-pro-max`] - full redesign not needed.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [14,15,18] | Blocked By: [4,5,9]

  **References**:
  - Pattern: `frontend/src/pages/Settings.tsx:13-237,1160-1419,1820-2050` - current provider/model/preset/test UI.
  - Pattern: `frontend/src/services/api.ts:69-150,222-260,922-1087` - shared axios/settings API wrappers.
  - API/Type: `frontend/src/types/index.ts:221-479,998-1181` - shared types to extend.
  - API/Type: Task 4 backend capability/settings schema.

  **Acceptance Criteria**:
  - [ ] `cd frontend && npm run test -- --run Settings` exits 0, or project-equivalent vitest filter exits 0.
  - [ ] `cd frontend && npm run build && npm run lint` exits 0.
  - [ ] Unsupported intensity options are disabled or rejected before save, and backend validation errors display as AntD error messages.
  - [ ] Advanced entity generation toggle persists only through backend API and defaults off in tests.

  **QA Scenarios**:
  ```
  Scenario: Supported model shows valid intensity options
    Tool: Bash
    Steps: cd frontend && npm run test -- --run Settings
    Expected: exit code 0; mocked OpenAI/Claude/Gemini capability payloads render only supported options and save normalized enum values
    Evidence: .sisyphus/evidence/task-13-settings-ui.log

  Scenario: Unsupported setting displays validation error
    Tool: Bash
    Steps: cd frontend && npm run test -- --run Settings
    Expected: exit code 0; test mocks backend preflight rejection and asserts visible AntD error text without saving invalid state
    Evidence: .sisyphus/evidence/task-13-settings-ui-error.log
  ```

  **Commit**: YES | Message: `frontend: add reasoning settings controls` | Files: [`frontend/src/pages/Settings.tsx`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `frontend/src/**/__tests__/**`]

- [x] 14. Add extraction candidate review UI to Characters, Organizations, and Careers pages

  **What to do**: Refactor `Characters.tsx`, `Organizations.tsx`, and `Careers.tsx` around extraction-first workflows. Add shared components such as `ExtractionCandidatePanel`, `CandidateMergeDialog`, `ProvenanceDrawer`, and `ManualReextractModal` under `frontend/src/components` or page-local components per repo style. Default tabs/sections should expose: 已入库, 正文发现, 待合并, 已拒绝/历史, and for careers/professions “职业时间线”. Hide/disable AI “generate new character/org/career” controls unless backend says advanced override is enabled; show policy explanation and manual edit/create remains available. Candidate actions call shared API wrappers for accept/reject/merge/rollback and refresh current projection.
  **Must NOT do**: Do not remove manual edit/create. Do not call endpoints with direct `axios`/`fetch` from pages if `frontend/src/services/api.ts` can wrap them. Do not force users to inspect raw JSON to understand evidence; show source chapter/snippet/confidence.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: multi-page workflow and review UX.
  - Skills: [`frontend-design`] - needed for clear candidate/provenance interactions.
  - Omitted: [`ui-ux-pro-max`] - no broad visual rebrand.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [16,18] | Blocked By: [10a,12,13]

  **References**:
  - Pattern: `frontend/src/pages/Characters.tsx:96-260` - current character list/create/edit/generate/import flow.
  - Pattern: `frontend/src/pages/Organizations.tsx:42-214` - current organization/member management.
  - Pattern: `frontend/src/pages/Careers.tsx:32-220` - current career CRUD/generation UI.
  - Pattern: `frontend/src/services/api.ts:69-150,222-260,922-1087` - shared API wrapper style.
  - API/Type: Task 10a/12 extraction and entity API contracts.

  **Acceptance Criteria**:
  - [ ] `cd frontend && npm run test -- --run extraction` exits 0, or equivalent vitest filter exits 0.
  - [ ] `cd frontend && npm run build && npm run lint` exits 0.
  - [ ] Candidate list renders evidence snippet, confidence, source chapter, status, and action buttons.
  - [ ] AI generate controls are absent/disabled by default and visible only when mocked backend capability says override enabled.
  - [ ] Accept/reject/merge UI paths refresh canonical list and candidate status from API mocks.

  **QA Scenarios**:
  ```
  Scenario: Candidate is accepted from review panel
    Tool: Bash
    Steps: cd frontend && npm run test -- --run extraction
    Expected: exit code 0; component test clicks accept, calls API wrapper, then displays accepted status and refreshed canonical entity
    Evidence: .sisyphus/evidence/task-14-entity-review-ui.log

  Scenario: AI generate button remains disabled when override is off
    Tool: Bash
    Steps: cd frontend && npm run test -- --run extraction
    Expected: exit code 0; mocked policy override false hides/disables AI generation and shows extraction-first explanation
    Evidence: .sisyphus/evidence/task-14-entity-review-ui-error.log
  ```

  **Commit**: YES | Message: `frontend: add extraction candidate review UI` | Files: [`frontend/src/pages/Characters.tsx`, `frontend/src/pages/Organizations.tsx`, `frontend/src/pages/Careers.tsx`, `frontend/src/components/**`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `frontend/src/**/__tests__/**`]

- [x] 15. Refactor Inspiration and WorldSetting UI for draft/result review instead of silent mutation

  **What to do**: Update inspiration mode so generated ideas remain drafts by default and can be saved as inspiration, converted to extraction candidates, or applied to world-setting result drafts without silently mutating canonical entities/world state. Update `WorldSetting.tsx` to show versioned generation results with statuses, diff against active snapshot, accept/reject/rollback actions, provider/model/reasoning metadata, and provenance/source links where available. Preserve existing world setting edit ability as manual active snapshot edit with provenance/audit entry.
  **Must NOT do**: Do not let inspiration directly create canonical character/org/profession by default. Do not overwrite `Project.world_*` until accept. Do not remove existing route paths.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: workflow redesign across inspiration/world pages.
  - Skills: [`frontend-design`] - needed for clear draft/result review UX.
  - Omitted: [`ui-ux-pro-max`] - no need for a complete visual system redesign.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [18] | Blocked By: [10b,13]

  **References**:
  - Pattern: `frontend/src/pages/Inspiration.tsx:51-260` - current inspiration chat/cache/retry/generation handoff.
  - Pattern: `frontend/src/pages/WorldSetting.tsx:12-119,128-246` - current display/edit/regenerate behavior.
  - Pattern: `backend/app/api/inspiration.py:13-243` - backend inspiration generation/refinement/template mapping.
  - API/Type: Task 8/10b world-setting result APIs.
  - External pattern: AI_NovelGenerator and Writingway research - staged idea/world/character/chapter workflow.

  **Acceptance Criteria**:
  - [ ] `cd frontend && npm run test -- --run world` exits 0, or equivalent vitest filter exits 0.
  - [ ] `cd frontend && npm run build && npm run lint` exits 0.
  - [ ] World generation result remains pending until accept, and UI diff clearly shows active vs candidate values.
  - [ ] Rollback action calls API and restores previous active snapshot in mocked test.
  - [ ] Inspiration “apply” actions create draft/candidate/result flows only, not canonical silent mutation.

  **QA Scenarios**:
  ```
  Scenario: World setting result is accepted after diff review
    Tool: Bash
    Steps: cd frontend && npm run test -- --run world
    Expected: exit code 0; test renders pending result, clicks accept, calls API, and active snapshot updates from mocked response
    Evidence: .sisyphus/evidence/task-15-world-inspiration-ui.log

  Scenario: Inspiration idea cannot silently create canonical entity
    Tool: Bash
    Steps: cd frontend && npm run test -- --run Inspiration
    Expected: exit code 0; apply-to-entity path creates candidate/draft API call only; canonical create endpoint is not called
    Evidence: .sisyphus/evidence/task-15-world-inspiration-ui-error.log
  ```

  **Commit**: YES | Message: `frontend: refactor inspiration and world result review` | Files: [`frontend/src/pages/Inspiration.tsx`, `frontend/src/pages/WorldSetting.tsx`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `frontend/src/**/__tests__/**`]

- [x] 16. Add relationship, affiliation, and profession timeline UI/query surfaces

  **What to do**: Add minimal timeline viewing/query UI for character-character relationships, character-organization affiliations, and character-profession assignments. Surface current projection and historical events by chapter/order. In character/org/career pages, add timeline panels that can filter by chapter, show start/change/end events, source evidence, confidence, and rollback/supersession status. Use existing project route structure; do not introduce a separate graph visualization route in Phase 1. Backend query should support `chapter_id` or `chapter_order` and return deterministic current-vs-history payloads.
  **Must NOT do**: Do not build a full graph visualization. Do not invent in-story dates when chapter/order is available. Do not hard-delete timeline events from UI actions.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - Reason: timeline UX must make temporal canon understandable.
  - Skills: [`frontend-design`] - needed for readable timeline/event states.
  - Omitted: [`ui-ux-pro-max`] - minimal functional timeline, not visual overhaul.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: [17,18] | Blocked By: [7,10b,12,14]

  **References**:
  - Pattern: `frontend/src/pages/Characters.tsx:96-260`, `Organizations.tsx:42-214`, `Careers.tsx:32-220` - pages to embed timeline panels.
  - Pattern: `frontend/src/App.tsx:1-73` - route map to preserve.
  - API/Type: Task 7 timeline service and Task 10b timeline API.
  - Data: `RelationshipTimelineEvent` from Task 2 and projections from Task 7.

  **Acceptance Criteria**:
  - [ ] `cd frontend && npm run test -- --run timeline` exits 0, or equivalent vitest filter exits 0.
  - [ ] `cd frontend && npm run build && npm run lint` exits 0.
  - [ ] Timeline UI shows different relationship/profession/org affiliation states for chapter 3, chapter 6, and chapter 10 using mocked data.
  - [ ] Ended relationships are absent from current projection after their `valid_to` chapter but remain visible in history mode.

  **QA Scenarios**:
  ```
  Scenario: Timeline panel changes state by chapter
    Tool: Bash
    Steps: cd frontend && npm run test -- --run timeline
    Expected: exit code 0; mocked chapter selector renders old state at chapter 3, changed state at chapter 6, ended state absent from current at chapter 10
    Evidence: .sisyphus/evidence/task-16-timeline-ui.log

  Scenario: History mode still shows ended relationship
    Tool: Bash
    Steps: cd frontend && npm run test -- --run timeline
    Expected: exit code 0; history tab includes ended event with evidence/confidence and supersession metadata
    Evidence: .sisyphus/evidence/task-16-timeline-ui-error.log
  ```

  **Commit**: YES | Message: `frontend: add relationship timeline view` | Files: [`frontend/src/pages/Characters.tsx`, `frontend/src/pages/Organizations.tsx`, `frontend/src/pages/Careers.tsx`, `frontend/src/components/**Timeline**`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `frontend/src/**/__tests__/**`]

- [ ] 17. Remove bypasses, document behavior, deprecate legacy services, and mark deprecated generation paths

  **What to do**: Audit all old entity/world generation paths and either route them through new policy/services or mark them deprecated with safe wrappers.

  **CharacterStateUpdateService deprecation**: Mark `CharacterStateUpdateService` as `@deprecated` with migration notes pointing to the extraction candidate pipeline. When `EXTRACTION_PIPELINE_ENABLED=True`, assert that no call site uses the legacy direct-mutation path without going through the Task 11 wrapper. Add static analysis test to detect direct usage.

  **auto_character_service / auto_organization_service deprecation**: Mark both as `@deprecated`. Their `create_*` methods should be routed through policy gate (Task 9) and extraction candidate pipeline. Add audit log for any remaining direct usage.

  Update README or project docs to describe: extraction-first workflow, automatic/manual triggers, advanced override policy, migration/backfill behavior, world-setting result accept/rollback, provider reasoning setting semantics, `EXTRACTION_PIPELINE_ENABLED` feature flag, and test commands. Ensure no code path can create canonical character/org/profession through AI without policy service. Add static/search-based regression tests for known call sites.
  **Must NOT do**: Do not remove user-facing routes without replacement. Do not document unsupported provider/model reasoning levels as guaranteed. Do not introduce a second API client in frontend.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: documentation plus cleanup guardrails.
  - Skills: [] - no extra skill required.
  - Omitted: [`frontend-design`] - no new UX components.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: [18] | Blocked By: [3,9,12,14,15,16]

  **References**:
  - Pattern: `backend/app/api/characters.py:197-260`, `organizations.py:218-260`, `careers.py:36-260` - old generation entrypoints.
  - Pattern: `backend/app/api/wizard_stream.py:1380-1520`, `backend/app/api/outlines.py:720-1039` - wizard/outline auto creation paths.
  - Pattern: `frontend/src/services/api.ts:69-150,222-260,922-1087` - ensure all new frontend calls go through shared wrapper.
  - Pattern: `README.md` and `AGENTS.md` - repo documentation conventions.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest tests/test_generation_bypass_audit.py` exits 0.
  - [ ] `cd frontend && npm run build && npm run lint && npm run test -- --run` exits 0.
  - [ ] Docs list exact commands: backend pytest, frontend build/lint/test, Docker build.
  - [ ] Static audit test fails if known old AI generation services are called without policy gate.

  **QA Scenarios**:
  ```
  Scenario: Static audit finds no ungated AI entity generation bypasses
    Tool: Bash
    Steps: cd backend && python -m pytest tests/test_generation_bypass_audit.py -q
    Expected: exit code 0; all known character/org/career AI creation call sites route through policy service
    Evidence: .sisyphus/evidence/task-17-cleanup-docs.log

  Scenario: Documentation commands are executable
    Tool: Bash
    Steps: cd frontend && npm run build && npm run lint && npm run test -- --run
    Expected: exit code 0; documented frontend commands match package scripts
    Evidence: .sisyphus/evidence/task-17-cleanup-docs-error.log
  ```

  **Commit**: YES | Message: `docs: document extraction-first refactor behavior` | Files: [`README.md`, `backend/tests/test_generation_bypass_audit.py`, `backend/app/api/**`, `backend/app/services/**`, `frontend/src/services/api.ts`]

- [ ] 18. Run integrated QA hardening and capture evidence bundle

  **What to do**: Execute the complete automated verification suite, Docker build, and deterministic smoke flows. Create an evidence bundle under `.sisyphus/evidence/` with command logs for backend pytest, frontend test/build/lint, Docker build, migration parity, provider capability tests, extraction/merge/timeline tests, and UI component tests. Fix failures discovered by this task; do not add new product scope. Summarize known limitations/deferred items in a final implementation note.
  **Must NOT do**: Do not waive failing tests. Do not mark final verification tasks F1-F4 as complete. Do not ask user to manually inspect; use captured logs/screenshots where needed.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: broad hands-on QA across backend/frontend/Docker.
  - Skills: [] - no extra skill required.
  - Omitted: [`git-master`] - do not perform git history operations unless separately requested.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: [F1,F2,F3,F4] | Blocked By: [1,5,11,13,14,15,16,17]

  **References**:
  - Command: `cd backend && python -m pytest` - full backend test suite added by this plan.
  - Command: `cd frontend && npm run test -- --run && npm run build && npm run lint` - frontend verification.
  - Command: `docker-compose build` - Docker-first build smoke.
  - Pattern: `Dockerfile:1-123`, `docker-compose.yml:1-140` - container build/runtime baseline.
  - Evidence path: `.sisyphus/evidence/` - required command logs.

  **Acceptance Criteria**:
  - [ ] `cd backend && python -m pytest` exits 0.
  - [ ] `cd frontend && npm run test -- --run && npm run build && npm run lint` exits 0.
  - [ ] `docker-compose build` exits 0.
  - [ ] Evidence files exist for every major command and every task QA scenario.
  - [ ] Final implementation note lists only deferred items already excluded by this plan.

  **QA Scenarios**:
  ```
  Scenario: Full automated suite passes
    Tool: Bash
    Steps: cd backend && python -m pytest && cd ../frontend && npm run test -- --run && npm run build && npm run lint
    Expected: exit code 0; logs show all backend/frontend tests and gates passing
    Evidence: .sisyphus/evidence/task-18-full-suite.log

  Scenario: Docker build smoke passes after frontend/backend integration
    Tool: Bash
    Steps: docker-compose build
    Expected: exit code 0; Dockerfile frontend build stage and backend runtime image build succeed
    Evidence: .sisyphus/evidence/task-18-docker-build.log
  ```

  **Commit**: YES | Message: `qa: add integrated refactor evidence` | Files: [`.sisyphus/evidence/**`, `backend/**`, `frontend/**`, `Dockerfile`, `docker-compose.yml`]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [ ] F1. Plan Compliance Audit — oracle
  - Verify every TODO acceptance criterion was executed and every evidence file exists.
  - Verify no source path outside this plan's scope was modified without explicit rationale.
  - Verify all final behavior matches user decisions: 自动+手动 extraction, advanced override, preserve/migrate, minimal tests, full timeline.
- [ ] F2. Code Quality Review — unspecified-high
  - Review backend service boundaries, migration quality, API contracts, provider abstractions, and frontend state handling.
  - Fail if provider-native fields leak into generic domain types or routers contain business orchestration.
- [ ] F3. Real Manual QA — unspecified-high (+ browser/Playwright if UI)
  - Run app through agent-controlled browser: settings, extraction candidates, accept/merge/reject, world setting result history, timeline view.
  - Capture screenshots/logs under `.sisyphus/evidence/final-ui-*`.
- [ ] F4. Scope Fidelity Check — deep
  - Confirm deferred items stayed out: graph visualization, custom ontology editor, shared lore DB, natural-language graph query, fine-tuning.
  - Confirm old projects still load and legacy data remains accessible.

## Commit Strategy
- Prefer one commit per TODO after its acceptance criteria pass.
- Never commit `.env`, credentials, local DB files, generated evidence screenshots unless intentionally under `.sisyphus/evidence` and approved by repo convention.
- Suggested commit sequence mirrors TODO order and uses `test:`, `db:`, `service:`, `api:`, `ai:`, `settings:`, `frontend:`, `qa:`, `docs:` prefixes.

## Success Criteria
- Existing projects retain all prior data and gain provenance/timeline compatibility without destructive migration.
- 正文 extraction can create candidates from chapter save, chapter generation, import, and manual re-run paths.
- Candidate accept/reject/merge/rollback is deterministic and audited.
- Characters, organizations, professions, affiliations, and relationships support chapter-based history and current projection.
- World-setting generation is versioned; active snapshot changes only on accept.
- Ordinary workflows cannot AI-generate canonical entities unless advanced/admin override is active.
- OpenAI Responses API works behind existing provider abstraction; OpenAI/Claude/Gemini thinking intensity options are model-gated and preflight validated.
- Backend tests, frontend build/lint/test, and Docker build pass.
