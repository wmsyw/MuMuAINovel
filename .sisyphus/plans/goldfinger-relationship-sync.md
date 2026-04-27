# 金手指管理与关系同步重构

## TL;DR

> **Summary**: 增加一等公民级别的“金手指管理”，并把新章节正文保存/验收后的关系与金手指提取统一到异步、幂等、带证据留痕的同步流水线中。章节保存不得被 AI 提取阻塞；低置信度、冲突和歧义进入待处理候选记录，不直接覆盖正式数据。
> **Deliverables**:
>
> - 后端新增金手指模型、历史、API、导入导出、同步候选审核 API。
> - 后端新增 `ChapterFactSyncService`、`GoldfingerSyncService`、`RelationshipMergeService`，统一章节正文保存/生成/分析后的事实同步。
> - 扩展提示词、分析解析、章节生成上下文，使金手指可从正文同步，也可反哺后续生成。
> - 前端新增与组织/职业/角色/关系同层级的 `金手指管理` 页面，包含管理、历史、导入导出、待处理审核。
> - 关系管理改为证据/历史/冲突可见，新增关系证据抽屉与待处理提示。
>   **Effort**: Large
>   **Parallel**: YES - 4 waves
>   **Critical Path**: Task 1 → Task 3 → Task 4/5 → Task 6/7 → Task 8 → Final Verification

## Context

### Original Request

用户原始需求：

> “增加一个金手指管理，用于管理金手指的类型、状态、任务、奖励等相关内容，同样是从小说正文中同步更新获取信息，位置与组织、职业、角色、关系等处于同一层级。重构优化关系管理功能，新章节生成验收后自动从新的正文中提取关系汇总更新。”

### Interview Summary

- Sync 入库策略：自动合并。
- 冲突处理：AI 合并，但必须保留旧信息和新正文证据。
- 金手指范围：核心字段 + 扩展规则 + 变更历史 + 导入导出。
- 失败/低置信度：创建待处理记录，不写正式数据。
- UI 形态：独立 `金手指管理` 页面，与组织、职业、角色、关系同层级。
- 测试策略：使用现有命令做验收型 QA，不新增正式测试框架。
- 触发范围：所有章节正文保存/验收，包括生成保存与手工编辑保存。
- 字段策略：半结构化；小型固定状态枚举 + JSON/text 存储类型、任务、奖励、规则、限制、触发条件、冷却等。
- CI 范围：不新增新的 CI workflow。

### Research Summary

- 后端实体路由模式：`backend/app/api/characters.py`、`careers.py`、`relationships.py`、`organizations.py` 使用 `APIRouter(prefix=...)`，在 `backend/app/main.py` 通过 `/api` 挂载。
- 前端工作区路由：`frontend/src/App.tsx` 管理 `/project/:projectId/*`；侧边栏在 `frontend/src/pages/ProjectDetail.tsx`（注意侧边栏有 `menuItems`、`menuItemsCollapsed`、`selectedKey` 三处需同步维护）。
- **关系模型双轨现状**：`CharacterRelationship`（旧表）被全代码库 11+ 个文件实际使用；`EntityRelationship`（新表，支持角色/组织端点）已定义但**从未在 service/API 层使用**。**⚡ 决策：本次统一收敛到 `EntityRelationship`，全面迁移所有调用者**。
- **提取/来源表现状**：`ExtractionRun`/`ExtractionCandidate`/`EntityProvenance` 已有完善字段（`candidate_type`、`content_hash`、`pipeline_version`、`payload`/`raw_payload`、`status` 含 pending/accepted/rejected/merged/superseded）。仅需新增 `review_required_reason` 字段。
- 章节保存路径：`update_chapter()` 是**纯同步 CRUD**（L258-388），不接受 `BackgroundTasks`；后台分析由 `analyze_chapter_background()` 独立函数承担（L827+）。
- **分析双入口**：`chapters.py` 的 `analyze_chapter_background()` 和 `memories.py` 的 `analyze_chapter()` **各自独立**调用 `CharacterStateUpdateService.update_from_analysis()`。**⚡ 决策：统一走 `ChapterFactSyncService`**。
- 章节生成上下文：`chapter_context_service.py` 定义 `OneToManyContext` 和 `OneToOneContext` 两个独立 dataclass，各有 `get_total_context_length()` 和 `context_stats`，目前均无 `goldfinger_context`。
- **前端组件目录**：`frontend/src/components/` 下无子目录，全部为顶层文件。**⚡ 决策：本次触发全面目录重组**。
- 验证基础：`backend/tests/` 含 `test_schema_contracts.py`、`test_migration_parity.py`、`test_golden_fixtures.py`、`fixture_schema.py`；前端有 `npm run test -- --run`、`npm run lint`、`npm run build`。

### Metis Review (gaps addressed)

- 已明确“accepted 正文”触发范围：手工保存、生成完成保存、局部重生成应用、`memories.py` 分析入口——全部统一走 `ChapterFactSyncService`。
- `chapters.py` 和 `memories.py` 两条分析路径合并为单一同步编排入口。
- 已复用 `ExtractionRun`/`ExtractionCandidate`/`EntityProvenance`（仅新增 `review_required_reason`），不新建审计系统。
- 已加入金手指生成上下文（`OneToManyContext` + `OneToOneContext` 双 dataclass 均新增 `goldfinger_context`）。
- 已要求导入导出版本化与 dry-run。
- 幂等键：`chapter_id + content_hash + pipeline_version + entity_type`（复用 `ExtractionRun` 联合索引）。
- **关系收敛**：全面迁移到 `EntityRelationship`，`CharacterRelationship` 标记为 deprecated。

### Oracle Architecture Review (incorporated)

- 章节保存路由只负责保存正文并创建/调度同步运行。同步调度条件：`"content" in update_data and chapter.content`（仅内容变化且非空时触发）。
- `ChapterFactSyncService` 覆盖 `chapters.py`（`analyze_chapter_background()`）和 `memories.py`（`analyze_chapter()`）两条路径。
- 关系写入统一收敛到 `EntityRelationship`；需迁移 11+ 个文件的 `CharacterRelationship` 引用（`character_state_update_service.py`、`chapter_context_service.py`、`auto_character_service.py`、`book_import_service.py`、`import_export_service.py`、`data_consistency.py`、`relationships.py`、`legacy_backfill_service.py`、`schemas/relationship.py`）。
- 金手指正式表只存当前状态和历史；AI 证据、候选、低置信度与冲突走提取/来源表。
- 金手指身份规则固定为 `project_id + normalized_name + optional owner_character_id/type`。
- 核心矛盾、归属歧义、低置信度一律进入待处理。
- 章节生成上下文中加入有界 goldfinger context（双 dataclass + `get_total_context_length` + `context_stats` 更新）。

## Work Objectives

### Core Objective

把“关系”和“金手指”统一建模为可从正文自动提取、可追溯、可审核、可导入导出、可参与后续章节生成的项目事实，且保存正文体验不被 AI 同步阻塞。

### Deliverables

- New file: `backend/app/models/goldfinger.py`
- New file: `backend/app/api/goldfingers.py`
- New file: `backend/app/api/sync.py`
- New file: `backend/app/services/chapter_fact_sync_service.py`
- New file: `backend/app/services/goldfinger_sync_service.py`
- New file: `backend/app/services/relationship_merge_service.py`
- Update: `backend/app/models/relationship.py`
- Update: `backend/app/services/prompt_service.py`
- Update: `backend/app/services/plot_analyzer.py`
- Update: `backend/app/services/chapter_context_service.py`
- Update: `backend/app/services/character_state_update_service.py`
- Update: `backend/app/services/auto_character_service.py` (CharacterRelationship → EntityRelationship)
- Update: `backend/app/services/book_import_service.py` (CharacterRelationship → EntityRelationship)
- Update: `backend/app/services/import_export_service.py` (CharacterRelationship → EntityRelationship)
- Update: `backend/app/services/legacy_backfill_service.py` (CharacterRelationship → EntityRelationship)
- Update: `backend/app/utils/data_consistency.py` (CharacterRelationship → EntityRelationship)
- Update: `backend/app/schemas/relationship.py` (adapt schema to EntityRelationship)
- Update: `backend/app/api/chapters.py`
- Update: `backend/app/api/memories.py`
- Update: `backend/app/main.py`
- Update: both `backend/alembic/postgres/versions/*` and `backend/alembic/sqlite/versions/*`
- New file: `frontend/src/pages/Goldfingers.tsx`
- Reorganize: `frontend/src/components/` (全面按功能分目录重组)
- New folder: `frontend/src/components/goldfingers/`
- Update: `frontend/src/services/api.ts`
- Update: `frontend/src/types/index.ts`
- Update: `frontend/src/App.tsx`
- Update: `frontend/src/pages/ProjectDetail.tsx`
- Update: `frontend/src/pages/Relationships.tsx`
- Update: `frontend/src/pages/RelationshipGraph.tsx` (完整适配来源/证据/置信度展示)

### Definition of Done (verifiable conditions with commands)

- `cd backend && pytest backend/tests` passes.
- `cd frontend && npm run test -- --run` passes.
- `cd frontend && npm run lint` passes.
- `cd frontend && npm run build` passes.
- API smoke evidence exists under `.sisyphus/evidence/` for goldfinger CRUD/import-export/sync review.
- Browser QA evidence exists under `.sisyphus/evidence/` for `/project/<projectId>/goldfingers` and relationship evidence UI.
- Re-saving identical chapter content does not duplicate extraction runs, goldfinger history, or relationship history.
- Low-confidence/conflicting extraction creates pending candidates only and does not mutate official goldfinger/relationship rows.

### Must Have

- 金手指正式数据模型：名称、归属角色、类型、状态、摘要、规则、任务、奖励、限制、触发条件、冷却、别名、元数据、来源/历史。
- 状态枚举 exactly: `latent`, `active`, `sealed`, `cooldown`, `upgrading`, `lost`, `completed`, `unknown`.
- 金手指 CRUD、历史、导出、导入 dry-run、导入正式执行。
- 所有章节正文保存/验收触发同步：手工保存、生成完成保存、局部重生成应用（如果存在）、背景分析、记忆/实体变化入口。
- 关系合并保留旧值、新正文证据、来源章节、置信度、候选记录、历史事件。
- 冲突/低置信度/归属歧义产生待处理记录。
- 前端 `金手指管理` 位于项目工作区同层级导航。
- 章节生成上下文包含有界金手指信息。

### Must NOT Have

- 不新增 CI workflow。
- 不新增独立 HTTP client；前端 API 只扩展 `frontend/src/services/api.ts`。
- 不在 `update_chapter()` 内执行阻塞式 AI 调用。
- 不让 AI 直接静默覆盖正式关系/金手指核心字段。
- 不只改 Postgres 或只改 SQLite migration；双 Alembic 树必须一致。
- 不重写整个角色/职业/组织模块。
- 不新增实时协作、可视化金手指图谱、通用万能实体框架。

## Verification Strategy

> ZERO HUMAN INTERVENTION - all verification is agent-executed.

- Test decision: 验收型 QA + existing pytest/Vitest/lint/build commands；不新增测试框架、不新增 CI workflow。
- QA policy: Every implementation task has happy-path and failure/edge scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`
- Backend commands:
  - `cd backend && pytest backend/tests`
- Frontend commands:
  - `cd frontend && npm run test -- --run`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
- Browser/API smoke must write concrete JSON, screenshots, or logs into `.sisyphus/evidence/`.

## Execution Strategy

### Parallel Execution Waves

> Target: 5-8 tasks per wave. This plan has a hard backend critical path because schema and sync contracts precede most feature slices.

Wave 1: Task 1 — schema/contracts/migrations foundation.
Wave 2: Task 2, Task 3, and Task 6 — goldfinger API/service, shared sync/pending API, and generation context after schema foundation.
Wave 3: Task 4, Task 5 — extraction/merge and relationship convergence refactor after sync foundation.
Wave 4: Task 7 and Task 8 — frontend module and relationship UI/regression after APIs/contracts are available.
Final Wave: F1-F4 review agents in parallel.

### Dependency Matrix

| Task                                      | Blocked By | Blocks             |
| ----------------------------------------- | ---------- | ------------------ |
| 1. Schema/contracts/migrations            | None       | 2, 3, 4, 5, 7, 8   |
| 2. Goldfinger backend API/service         | 1          | 7, 8               |
| 3. Shared sync orchestration/review API   | 1          | 4, 5, 7, 8         |
| 4. Goldfinger extraction/parser/merge     | 1, 3       | 6, 8               |
| 5. Relationship merge/refactor/triggers   | 1, 3       | 8                  |
| 6. Goldfinger generation context          | 1, 2       | 8                  |
| 7. Frontend goldfinger page/API/review UI | 2, 3       | 8                  |
| 8. Relationship provenance UI/regression  | 5, 7       | Final Verification |

### Agent Dispatch Summary

| Wave  | Task Count | Recommended Categories                           |
| ----- | ---------: | ------------------------------------------------ |
| 1     |          1 | deep                                             |
| 2     |          2 | deep, unspecified-high                           |
| 3     |          3 | deep, unspecified-high                           |
| 4     |          2 | visual-engineering, unspecified-high             |
| Final |          4 | oracle, unspecified-high, unspecified-high, deep |

## TODOs

> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Add schema contracts, goldfinger models, and dual migrations

  **What to do**:
  - Add SQLAlchemy model file `backend/app/models/goldfinger.py` with canonical `Goldfinger` and `GoldfingerHistoryEvent`.
  - Required `Goldfinger` fields:
    - `id`, `project_id`, `name`, `normalized_name`, `owner_character_id`, `owner_character_name`, `type`, `status`, `summary`.
    - Flexible JSON/text fields: `rules`, `tasks`, `rewards`, `limits`, `trigger_conditions`, `cooldown`, `aliases`, `metadata`.
    - audit fields: `created_at`, `updated_at`, `created_by`, `updated_by`, `source`, `confidence`, `last_source_chapter_id`.
  - Required status enum exactly: `latent`, `active`, `sealed`, `cooldown`, `upgrading`, `lost`, `completed`, `unknown`.
  - Add `GoldfingerHistoryEvent` with `goldfinger_id`, `project_id`, `chapter_id`, `event_type`, `old_value`, `new_value`, `evidence_excerpt`, `confidence`, `source_type`, `created_at`.
  - Extend `ExtractionCandidate` in `backend/app/models/relationship.py` with `review_required_reason` field only. Existing fields (`candidate_type`, `content_hash` on `ExtractionRun`, `pipeline_version`, `payload`/`raw_payload`, `status`, `source_chapter_id`) are already sufficient — do NOT re-add them.
  - Add mirrored Alembic migrations in both `backend/alembic/postgres/versions/` and `backend/alembic/sqlite/versions/`.
  - Update model imports/metadata registration so migrations and app startup see the new tables.
  - Add/extend backend tests under `backend/tests/` for schema contract and migration parity.

  **Must NOT do**:
  - Do not put all goldfinger facts only into generic JSON without canonical identity/status columns.
  - Do not create migrations for only one database backend.
  - Do not remove or rename existing relationship tables.

  **Recommended Agent Profile**:
  - Category: `deep` - schema changes affect backend, migrations, extraction provenance, and future frontend contracts.
  - Skills: [] - no special external skill required.
  - Omitted: [`frontend-design`] - no UI work in this task.

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: [2, 3, 4, 5, 7, 8] | Blocked By: []

  **References**:
  - Pattern: `backend/app/models/relationship.py` - relationship, organization, extraction/provenance/history model style to extend.
  - Pattern: `backend/app/models/career.py` - entity model style for canonical domain tables.
  - Pattern: `backend/alembic/postgres/versions/` and `backend/alembic/sqlite/versions/` - dual migration tree convention.
  - Test: `backend/tests/test_harness_smoke.py`, `backend/tests/test_golden_fixtures.py`, `backend/tests/fixture_schema.py` - current pytest style and fixture/schema helpers.

  **Acceptance Criteria**:
  - [ ] `backend/app/models/goldfinger.py` exists and defines `Goldfinger` and `GoldfingerHistoryEvent`.
  - [ ] Both Alembic trees contain equivalent goldfinger/extraction metadata migrations.
  - [ ] `cd backend && pytest backend/tests` passes.
  - [ ] Evidence file `.sisyphus/evidence/task-1-schema-migrations.txt` contains migration/table summary and pytest result.

  **QA Scenarios**:

  ```
  Scenario: Create schema from migrations
    Tool: Bash
    Steps: Run `cd backend && pytest backend/tests` after adding schema/migration parity coverage.
    Expected: all backend tests pass; no missing table/column/import error; both SQLite and Postgres migration files are present.
    Evidence: .sisyphus/evidence/task-1-schema-migrations.txt

  Scenario: Invalid status is rejected
    Tool: Bash
    Steps: Run the backend schema/API test that attempts to create a goldfinger with status `super_active`.
    Expected: validation fails with a deterministic 422 or model validation error; no row is inserted.
    Evidence: .sisyphus/evidence/task-1-invalid-status.txt
  ```

  **Commit**: YES | Message: `feat(db): add goldfinger schema and sync provenance fields` | Files: [`backend/app/models/goldfinger.py`, `backend/app/models/relationship.py`, `backend/alembic/postgres/versions/*`, `backend/alembic/sqlite/versions/*`, `backend/tests/*`]

- [ ] 2. Implement goldfinger backend API, service, history, and import/export

  **What to do**:
  - Add `backend/app/api/goldfingers.py` and register it in `backend/app/main.py` under `/api`.
  - Add service methods for list/create/detail/update/delete/history/export/import dry-run/import apply.
  - Endpoint contract under `/api/goldfingers`:
    - `GET /api/goldfingers/project/{project_id}` list.
    - `POST /api/goldfingers/project/{project_id}` create.
    - `GET /api/goldfingers/{goldfinger_id}` detail.
    - `PUT /api/goldfingers/{goldfinger_id}` update.
    - `DELETE /api/goldfingers/{goldfinger_id}` soft-delete or delete consistent with existing entity modules.
    - `GET /api/goldfingers/{goldfinger_id}/history` history events.
    - `GET /api/goldfingers/project/{project_id}/export` export payload.
    - `POST /api/goldfingers/project/{project_id}/import/dry-run` validate import without writes.
    - `POST /api/goldfingers/project/{project_id}/import` apply validated import.
  - Import/export payload version exactly `goldfinger-card.v1`.
  - All endpoints must use `request.state.user_id` and existing project access verification pattern.
  - Manual create/update/import must create provenance/history events with `source_type=manual` or `source_type=import`.
  - Add backend API tests or smoke coverage for CRUD, history, export, dry-run import, apply import, auth/project scoping.

  **Must NOT do**:
  - Do not trust client-supplied user IDs.
  - Do not silently overwrite existing goldfinger identity on import; dry-run must report conflicts first.
  - Do not add a separate FastAPI app or ad-hoc auth path.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - backend API/service work with auth, validation, and import/export contracts.
  - Skills: []
  - Omitted: [`frontend-design`] - frontend comes later.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [7, 8] | Blocked By: [1]

  **References**:
  - Pattern: `backend/app/api/characters.py` - project-scoped entity CRUD conventions.
  - Pattern: `backend/app/api/careers.py` - domain service/router split and Chinese route tags.
  - Pattern: `backend/app/api/organizations.py` - workspace-level entity API patterns.
  - Pattern: `backend/app/main.py` - router mounting.

  **Acceptance Criteria**:
  - [ ] All listed endpoints exist and are mounted under `/api/goldfingers`.
  - [ ] Export response contains `version: "goldfinger-card.v1"`.
  - [ ] Dry-run import returns validation report and writes zero canonical rows.
  - [ ] Apply import writes canonical rows and history/provenance.
  - [ ] `cd backend && pytest backend/tests` passes.

  **QA Scenarios**:

  ```
  Scenario: CRUD and history happy path
    Tool: Bash
    Steps: Use backend API smoke/test client to create project goldfinger `天命系统` with status `active`, update status to `cooldown`, then fetch detail and history.
    Expected: create returns 200/201 with name `天命系统`; detail returns status `cooldown`; history count is at least 2 with manual source events.
    Evidence: .sisyphus/evidence/task-2-goldfinger-crud.json

  Scenario: Import dry-run conflict does not mutate data
    Tool: Bash
    Steps: Submit `goldfinger-card.v1` payload containing duplicate normalized name for existing `天命系统` to `/import/dry-run`, then fetch list.
    Expected: dry-run returns conflict report; list count remains unchanged; no history event is added.
    Evidence: .sisyphus/evidence/task-2-import-dry-run.json
  ```

  **Commit**: YES | Message: `feat(api): add goldfinger management endpoints` | Files: [`backend/app/api/goldfingers.py`, `backend/app/main.py`, `backend/app/services/*goldfinger*`, `backend/tests/*`]

- [ ] 3. Build shared chapter fact sync orchestration and pending review API

  **What to do**:
  - Add `backend/app/services/chapter_fact_sync_service.py`.
  - Implement public methods:
    - `schedule_for_chapter(project_id, chapter_id, content, source, entity_types=["relationship", "goldfinger"])`.
    - `process_run(run_id)`.
    - `retry_run(run_id)`.
    - `build_idempotency_key(chapter_id, content_hash_or_version, extractor_version, entity_type)`.
    - `record_candidate(run_id, entity_type, payload, confidence, evidence_excerpt, review_required_reason)`.
  - Persist `ExtractionRun(status=pending)` before scheduling background work.
  - Use in-process background scheduling only after persistence; failed background work must leave retryable run state.
  - Add `backend/app/api/sync.py` and register in `backend/app/main.py`.
  - API endpoints:
    - `GET /api/sync/project/{project_id}/runs` list runs.
    - `GET /api/sync/project/{project_id}/candidates` list pending candidates.
    - `POST /api/sync/runs/{run_id}/retry` retry failed/pending run.
    - `POST /api/sync/candidates/{candidate_id}/approve` apply candidate through correct merge service.
    - `POST /api/sync/candidates/{candidate_id}/reject` reject with reason.
  - Ensure approvals route to goldfinger or relationship merge by `entity_type`.
  - Add tests for idempotency and candidate approval/rejection.

  **Must NOT do**:
  - Do not call AI inline from chapter save endpoint.
  - Do not create duplicate runs for identical chapter/content/extractor/entity_type.
  - Do not apply pending candidates directly without merge service.

  **Recommended Agent Profile**:
  - Category: `deep` - central orchestration affects persistence, idempotency, background execution, and review APIs.
  - Skills: []
  - Omitted: [`frontend-design`] - API only.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [4, 5, 7, 8] | Blocked By: [1]

  **References**:
  - Pattern: `backend/app/api/chapters.py` - current background analysis scheduling and chapter save boundaries.
  - Pattern: `backend/app/models/relationship.py` - extraction run/candidate/provenance concepts.
  - Pattern: `backend/app/main.py` - router mounting.

  **Acceptance Criteria**:
  - [ ] `schedule_for_chapter` creates one run per unique idempotency key and returns existing run on duplicate content.
  - [ ] `update_chapter()` can schedule a run without waiting for AI completion once wired by later tasks.
  - [ ] Pending candidate approve/reject endpoints update status and preserve audit reason.
  - [ ] `cd backend && pytest backend/tests` passes.

  **QA Scenarios**:

  ```
  Scenario: Idempotent sync scheduling
    Tool: Bash
    Steps: In backend test/smoke, call `schedule_for_chapter` twice with same chapter id, content hash, extractor version, and entity type.
    Expected: exactly one `ExtractionRun` exists; second call returns existing run id; no duplicate candidates are created.
    Evidence: .sisyphus/evidence/task-3-idempotency.json

  Scenario: Retry failed run
    Tool: Bash
    Steps: Force a run into failed state, call `POST /api/sync/runs/{run_id}/retry`, then list runs.
    Expected: run becomes pending/processing according to implementation state machine; retry count increments; original failure message remains auditable.
    Evidence: .sisyphus/evidence/task-3-retry-run.json
  ```

  **Commit**: YES | Message: `feat(sync): add chapter fact sync orchestration` | Files: [`backend/app/services/chapter_fact_sync_service.py`, `backend/app/api/sync.py`, `backend/app/main.py`, `backend/tests/*`]

- [ ] 4. Add goldfinger extraction prompts, parser, and merge service

  **What to do**:
  - Extend `backend/app/services/prompt_service.py` so chapter analysis asks for `goldfinger_changes` alongside existing relationship/organization/career changes.
  - Extend `backend/app/services/plot_analyzer.py` parser/schema handling for `goldfinger_changes`.
  - `goldfinger_changes` item fields must include:
    - `name`, `normalized_name`, `owner_character_name`, `owner_character_id`, `type`, `status`, `summary`, `rules`, `tasks`, `rewards`, `limits`, `trigger_conditions`, `cooldown`, `aliases`, `operation`, `evidence_excerpt`, `confidence`, `conflict_hint`.
  - Add `backend/app/services/goldfinger_sync_service.py`.
  - Identity rule: `project_id + normalized_name + optional owner_character_id/type`.
  - Auto-merge additive facts: aliases, new usage examples, new tasks/rewards, evidence-backed history events, non-conflicting summaries.
  - Pending-only conditions: confidence below threshold, owner ambiguity, normalized name collision, status contradiction, core rule/limit contradiction, missing evidence excerpt for destructive operation.
  - Every applied AI change writes `GoldfingerHistoryEvent` and `EntityProvenance`/candidate decision details.
  - Add service tests for happy extraction, pending conflict, duplicate/idempotent extraction.

  **Must NOT do**:
  - Do not overwrite `rules`, `limits`, `owner_character_id`, or `status` without contradiction detection and evidence.
  - Do not accept AI output lacking source evidence for destructive/removal operations.
  - Do not bypass `ChapterFactSyncService` candidate recording.

  **Recommended Agent Profile**:
  - Category: `deep` - AI extraction schema and merge semantics require careful deterministic rules.
  - Skills: []
  - Omitted: [`frontend-design`] - no frontend in this task.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [6, 8] | Blocked By: [1, 3]

  **References**:
  - Pattern: `backend/app/services/prompt_service.py` - existing relationship/organization/career analysis prompt structure.
  - Pattern: `backend/app/services/plot_analyzer.py` - parser/analysis output normalization.
  - Pattern: `backend/app/services/character_state_update_service.py` - existing entity updates to replace/coordinate with.

  **Acceptance Criteria**:
  - [ ] Analysis result can contain `goldfinger_changes` with all required fields.
  - [ ] High-confidence non-conflicting goldfinger fact auto-merges into canonical table and history.
  - [ ] Low-confidence/conflicting fact creates pending candidate only.
  - [ ] Re-processing same run does not duplicate canonical rows or history.
  - [ ] `cd backend && pytest backend/tests` passes.

  **QA Scenarios**:

  ```
  Scenario: Extract and merge goldfinger from accepted chapter
    Tool: Bash
    Steps: Feed fixed chapter text containing `林墨激活天命系统，任务是在三日内救下师姐，奖励为悟性提升` through sync processing.
    Expected: canonical goldfinger `天命系统` exists with status `active`; task/reward fields contain the extracted facts; history includes source chapter and evidence excerpt.
    Evidence: .sisyphus/evidence/task-4-goldfinger-extract.json

  Scenario: Conflicting owner becomes pending
    Tool: Bash
    Steps: Existing `天命系统` belongs to `林墨`; process text claiming the same normalized name belongs to another character with low/ambiguous evidence.
    Expected: official owner remains `林墨`; one pending candidate exists with `review_required_reason` explaining owner conflict.
    Evidence: .sisyphus/evidence/task-4-owner-conflict.json
  ```

  **Commit**: YES | Message: `feat(sync): extract and merge goldfinger facts` | Files: [`backend/app/services/prompt_service.py`, `backend/app/services/plot_analyzer.py`, `backend/app/services/goldfinger_sync_service.py`, `backend/tests/*`]

- [ ] 5. Converge to EntityRelationship, add relationship merge, and wire all sync paths

  **What to do**:
  - Add `backend/app/services/relationship_merge_service.py`.
  - **全面迁移 `CharacterRelationship` → `EntityRelationship`**：
    - `character_state_update_service.py`：`_update_relationships()` 改写为写入 `EntityRelationship`，委托 `RelationshipMergeService`。
    - `chapter_context_service.py`：关系查询从 `CharacterRelationship` 迁移到 `EntityRelationship`。
    - `auto_character_service.py`：自动角色创建时的关系写入迁移到 `EntityRelationship`。
    - `book_import_service.py`：导入关系的写入/查询迁移到 `EntityRelationship`。
    - `import_export_service.py`：导出关系迁移到读取 `EntityRelationship`。
    - `legacy_backfill_service.py`：回填逻辑迁移到 `EntityRelationship`。
    - `data_consistency.py`：一致性检查迁移到 `EntityRelationship`。
    - `relationships.py`（API）：CRUD 端点和 graph 端点全部迁移到 `EntityRelationship`。
    - `schemas/relationship.py`：Pydantic schema 适配 `EntityRelationship` 字段。
  - 添加 Alembic 数据迁移：将现有 `CharacterRelationship` 数据批量复制到 `EntityRelationship`（`from_entity_type=character`, `to_entity_type=character`）。
  - `CharacterRelationship` 表保留但标记为 `@deprecated`，不再有任何写入。
  - Relationship merge 必须保留：端点/角色、关系类型、方向、摘要/状态、来源章节、证据摘录、置信度、旧值、新值、决策。
  - 冲突/待处理条件：端点解析歧义、类型矛盾、方向矛盾、无高置信度证据的破坏性移除、置信度低于阈值。
  - Update `backend/app/api/chapters.py`：`update_chapter()` 在 save/commit 后调度 `ChapterFactSyncService.schedule_for_chapter(...)`，条件为 `"content" in update_data and chapter.content`。使用 `asyncio.create_task()` 非阻塞调度。
  - Update `generate_chapter_content_stream()` 在生成内容保存后调度 sync。
  - Update `analyze_chapter_background()` 使分析衍生的关系/金手指事实走共享 sync/merge 路径。
  - **统一 `memories.py` 分析路径**：`analyze_chapter()` 中的 `CharacterStateUpdateService.update_from_analysis()` 调用改为通过 `ChapterFactSyncService.schedule_for_chapter()` fire-and-forget 调度，不影响同步返回。
  - 添加测试：手工保存、生成保存、重复保存、冲突关系待处理、EntityRelationship 数据迁移验证。

  **Must NOT do**:
  - Do not leave any file still writing to `CharacterRelationship`.
  - Do not break existing relationship API/frontend consumers（API 响应 schema 保持兼容）。
  - Do not fail chapter save because relationship/goldfinger AI extraction fails.

  **Recommended Agent Profile**:
  - Category: `deep` - high-risk refactor across 11+ files, relationship convergence, chapter save, analysis, memory paths.
  - Skills: []
  - Omitted: [`frontend-design`] - UI evidence appears in later tasks.

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: [8] | Blocked By: [1, 3]

  **References**:
  - Pattern: `backend/app/services/character_state_update_service.py` - existing relationship and organization update flow.
  - Pattern: `backend/app/api/chapters.py` - `update_chapter()`, generation save, `analyze_chapter_background()`.
  - Pattern: `backend/app/api/memories.py` - additional analysis/entity-change write path that must be unified.
  - Pattern: `backend/app/api/relationships.py` - current relationship API compatibility expectations.
  - **Migration scope**: `character_state_update_service.py`, `chapter_context_service.py`, `auto_character_service.py`, `book_import_service.py`, `import_export_service.py`, `data_consistency.py`, `legacy_backfill_service.py`, `relationships.py`, `schemas/relationship.py`.

  **Acceptance Criteria**:
  - [ ] Zero files write to `CharacterRelationship`; all writes go to `EntityRelationship`.
  - [ ] Data migration copies existing `CharacterRelationship` rows to `EntityRelationship`.
  - [ ] Manual `update_chapter()` schedules sync only when content changes and is non-empty.
  - [ ] Generated chapter completion schedules sync after save.
  - [ ] `memories.py` `analyze_chapter()` delegates to `ChapterFactSyncService` instead of direct writes.
  - [ ] Existing relationship UI/API continues to receive compatible data.
  - [ ] Conflicting relationship update creates pending candidate.
  - [ ] `cd backend && pytest backend/tests` passes.

  **QA Scenarios**:

  ```
  Scenario: Manual accepted text save updates relationship via EntityRelationship
    Tool: Bash
    Steps: Save chapter text stating relationship change through `update_chapter()`, process sync, query relationship API.
    Expected: chapter save returns success before AI completion; after sync, `EntityRelationship` contains updated relationship; `CharacterRelationship` is not written to.
    Evidence: .sisyphus/evidence/task-5-entity-relationship-convergence.json

  Scenario: memories.py analysis path uses ChapterFactSyncService
    Tool: Bash
    Steps: Call `POST /api/memories/projects/{pid}/analyze-chapter/{cid}`, verify sync run is created.
    Expected: `ExtractionRun` created via `ChapterFactSyncService`; no direct `CharacterRelationship` write in memories.py code path.
    Evidence: .sisyphus/evidence/task-5-memories-unified.json

  Scenario: Same generated content does not duplicate history
    Tool: Bash
    Steps: Simulate generated chapter content saved twice with same content hash and run sync twice.
    Expected: one extraction run per entity type; no duplicate relationship history events.
    Evidence: .sisyphus/evidence/task-5-generated-idempotency.json
  ```

  **Commit**: YES | Message: `refactor(relationships): converge to EntityRelationship and unify sync paths` | Files: [`backend/app/services/relationship_merge_service.py`, `backend/app/services/character_state_update_service.py`, `backend/app/services/chapter_context_service.py`, `backend/app/services/auto_character_service.py`, `backend/app/services/book_import_service.py`, `backend/app/services/import_export_service.py`, `backend/app/services/legacy_backfill_service.py`, `backend/app/utils/data_consistency.py`, `backend/app/api/chapters.py`, `backend/app/api/memories.py`, `backend/app/api/relationships.py`, `backend/app/schemas/relationship.py`, `backend/alembic/*/versions/*`, `backend/tests/*`]

- [ ] 6. Add bounded goldfinger context to chapter generation

  **What to do**:
  - Update `backend/app/services/chapter_context_service.py` to load active/relevant goldfingers for project/chapter context.
  - Add `goldfinger_context: Optional[str] = None` field to **both** `OneToManyContext` (L23-76) and `OneToOneContext` (L78-127) dataclasses in `chapter_context_service.py`.
  - Update `get_total_context_length()` method in **both** dataclasses to include `goldfinger_context` length.
  - Update `context_stats` dict in `OneToManyContextBuilder.build()` and `OneToOneContextBuilder.build()` to include `goldfinger_length` and `goldfinger_count` entries.
  - Limits:
    - max 8 goldfingers per generated context;
    - max 3 recent history events per goldfinger;
    - max 300 Chinese chars per goldfinger summary;
    - prioritize owner-character relevance, active/cooldown/upgrading status, recent evidence, and explicit chapter outline relevance.
  - Update prompt formatting in `prompt_service.py` or generation prompt builder to include bounded goldfinger context.
  - Add tests/smokes ensuring context includes goldfinger data and remains bounded.

  **Must NOT do**:
  - Do not dump full JSON/history into every prompt.
  - Do not include pending/unapproved AI candidates as official generation context.
  - Do not break existing generation context keys consumed by chapter generation.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - backend prompt/context integration with token-budget constraints.
  - Skills: []
  - Omitted: [`frontend-design`] - no UI here.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: [8] | Blocked By: [1, 2]

  **References**:
  - Pattern: `backend/app/services/chapter_context_service.py` - existing chapter generation context assembly.
  - Pattern: `backend/app/services/prompt_service.py` - prompt formatting and chapter analysis/generation text.

  **Acceptance Criteria**:
  - [ ] Generation context includes approved goldfinger facts under `goldfinger_context`.
  - [ ] Context excludes pending candidates.
  - [ ] Context obeys max 8 goldfingers, max 3 history events, max 300 Chinese chars per summary.
  - [ ] `cd backend && pytest backend/tests` passes.

  **QA Scenarios**:

  ```
  Scenario: Relevant goldfinger appears in generation context
    Tool: Bash
    Steps: Create active `天命系统` for protagonist and request chapter context build.
    Expected: `goldfinger_context` contains `天命系统`, current status, concise rules/tasks/rewards summary, and no pending candidates.
    Evidence: .sisyphus/evidence/task-6-generation-context.json

  Scenario: Context is bounded
    Tool: Bash
    Steps: Create 12 goldfingers with long summaries and histories; build context.
    Expected: at most 8 goldfingers, at most 3 history events each, each summary truncated/summarized to 300 Chinese chars or less.
    Evidence: .sisyphus/evidence/task-6-context-bounds.json
  ```

  **Commit**: YES | Message: `feat(generation): include bounded goldfinger context` | Files: [`backend/app/services/chapter_context_service.py`, `backend/app/services/prompt_service.py`, `backend/tests/*`]

- [ ] 7. Add frontend goldfinger route, API, management, history, import/export, and pending review

  **What to do**:
  - Update `frontend/src/types/index.ts` with `Goldfinger`, `GoldfingerHistoryEvent`, `GoldfingerImportPayload`, `GoldfingerImportDryRunResult`, `SyncRun`, `ExtractionCandidate` types.
  - Extend `frontend/src/services/api.ts` with `goldfingerApi` and `syncApi` only; no new client.
  - Add route `/project/:projectId/goldfingers` in `frontend/src/App.tsx`.
  - Add sidebar/nav item `金手指管理` in `frontend/src/pages/ProjectDetail.tsx` — **三处同步修改**：
    - `menuItems`（展开菜单，`创作管理` 分组下添加）
    - `menuItemsCollapsed`（折叠菜单，扁平列表中添加）
    - `selectedKey` 的 `useMemo`（添加 `if (path.includes('/goldfingers')) return 'goldfingers';` 匹配规则）
    - 建议图标：`ThunderboltOutlined`（⚡）或 `FireOutlined`（🔥）
  - Add page `frontend/src/pages/Goldfingers.tsx`.
  - **全面组件目录重组**：将 `frontend/src/components/` 下的现有顶层组件按功能分目录：
    - `components/chapter/` — `ChapterAnalysis.tsx`, `ChapterContentComparison.tsx`, `ChapterReader.tsx`, `ChapterRegenerationModal.tsx`
    - `components/character/` — `CharacterCard.tsx`, `CharacterCareerCard.tsx`
    - `components/generation/` — `AIProjectGenerator.tsx`, `ExpansionPlanEditor.tsx`
    - `components/progress/` — `SSELoadingOverlay.tsx`, `SSEProgressBar.tsx`, `SSEProgressModal.tsx`
    - `components/layout/` — `AppFooter.tsx`, `FloatingIndexPanel.tsx`, `MemorySidebar.tsx`
    - `components/common/` — `AnnotatedText.tsx`, `CardStyles.tsx`, `ProtectedRoute.tsx`, `ThemeSwitch.tsx`, `UserMenu.tsx`
    - `components/modal/` — `AnnouncementModal.tsx`, `ChangelogModal.tsx`, `ChangelogFloatingButton.tsx`, `PartialRegenerateModal.tsx`, `PartialRegenerateToolbar.tsx`
    - `components/theme/` — `SpringFestival.tsx`, `SpringFestival.css`
    - `components/goldfingers/` — 新增金手指管理组件
  - 更新所有引用路径（`import` 语句）以反映新目录结构。
  - Add components under `frontend/src/components/goldfingers/`:
    - `GoldfingerList`, `GoldfingerEditor`, `GoldfingerHistoryDrawer`, `GoldfingerImportExportModal`, `GoldfingerPendingReviewPanel` or equivalent names.
  - UI must support list/create/edit/delete/detail/history/export/import dry-run/import apply.
  - Pending review UI must show source chapter, evidence excerpt, confidence, proposed change diff, review reason, approve/reject actions.
  - Use existing Ant Design patterns and Chinese copy style.
  - Add/extend Vitest smoke tests if existing test pattern supports it; otherwise rely on build/lint plus browser QA evidence.

  **Must NOT do**:
  - Do not create a second axios/fetch wrapper.
  - Do not place goldfinger as a child tab inside relationships; it must be independent same-level workspace page.
  - Do not hide pending review evidence; review items must be actionable.

  **Recommended Agent Profile**:
  - Category: `visual-engineering` - frontend page, interaction states, management UI, evidence display.
  - Skills: [`frontend-design`] - polished and accessible React/Ant Design UI.
  - Omitted: [`mobile-ios-design`] - not an iOS task.

  **Parallelization**: Can Parallel: YES | Wave 4 | Blocks: [8] | Blocked By: [2, 3]

  **References**:
  - Pattern: `frontend/src/pages/Characters.tsx` - entity list/detail/edit page style.
  - Pattern: `frontend/src/pages/Careers.tsx` - workspace domain management style.
  - Pattern: `frontend/src/pages/Organizations.tsx` - same-level entity page pattern.
  - Pattern: `frontend/src/services/api.ts` - shared axios and API grouping.
  - Pattern: `frontend/src/App.tsx` - protected route map.
  - Pattern: `frontend/src/pages/ProjectDetail.tsx` - sidebar/nav wiring.

  **Acceptance Criteria**:
  - [ ] `/project/:projectId/goldfingers` renders page title `金手指管理`.
  - [ ] Sidebar contains `金手指管理` at same level as organization/career/character/relationship items.
  - [ ] Page supports create/edit/history/import-export/pending review against backend API contracts.
  - [ ] `cd frontend && npm run test -- --run` passes.
  - [ ] `cd frontend && npm run lint` passes.
  - [ ] `cd frontend && npm run build` passes.

  **QA Scenarios**:

  ```
  Scenario: Goldfinger management page happy path
    Tool: Playwright or browser automation
    Steps: Navigate to `/project/<projectId>/goldfingers`; click create button with accessible text `新建金手指`; fill name `天命系统`, type `系统`, status `active`; save; open detail/history.
    Expected: title `金手指管理` visible; created item `天命系统` visible; history drawer shows manual create event.
    Evidence: .sisyphus/evidence/task-7-goldfinger-page.png

  Scenario: Import dry-run validation error is visible
    Tool: Playwright or browser automation
    Steps: Open import modal; upload/paste invalid payload with wrong version; click dry-run validate.
    Expected: validation error displays expected version `goldfinger-card.v1`; no new list item appears.
    Evidence: .sisyphus/evidence/task-7-import-validation.png
  ```

  **Commit**: YES | Message: `feat(frontend): add goldfinger workspace management` | Files: [`frontend/src/pages/Goldfingers.tsx`, `frontend/src/components/goldfingers/*`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `frontend/src/App.tsx`, `frontend/src/pages/ProjectDetail.tsx`, `frontend/src/__tests__/*`]

- [ ] 8. Add relationship provenance UI and end-to-end regression hardening

  **What to do**:
  - Update `frontend/src/pages/Relationships.tsx` to show relationship provenance/metadata when available.
  - Add evidence drawer/panel showing source chapter, evidence excerpt, confidence, merge history, and pending conflict badge.
  - **完整适配** `frontend/src/pages/RelationshipGraph.tsx`：
    - 关系详情面板追加"来源章节"、"置信度"、"证据摘录"字段展示。
    - 边（link）的 tooltip/detail 增加 provenance 信息。
    - 待处理关系显示特殊标记/徽章（如虚线边或橙色标记）。
  - Ensure sync pending review UI from Task 7 can review both goldfinger and relationship candidates through `syncApi`.
  - Run full backend and frontend verification commands.
  - Execute end-to-end smoke:
    1. create/open project;
    2. create characters `林墨` and `苏青` if fixture requires;
    3. save accepted chapter text containing relationship and goldfinger facts;
    4. process/retry sync if needed;
    5. verify relationship summary and goldfinger card are updated;
    6. verify conflicting update enters pending review;
    7. approve/reject candidate and verify UI/API state.
  - Gather all evidence files under `.sisyphus/evidence/`.

  **Must NOT do**:
  - Do not rely on “visual confirmation by user”; evidence must be agent-produced.
  - Do not mark final verification tasks complete without user explicit okay after results are presented.
  - Do not hide failed QA; fix failures before final verification.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - cross-stack regression and UI/API hardening.
  - Skills: [`frontend-design`] - relationship evidence UI polish.
  - Omitted: [`git-master`] - commit operations only if user/workflow explicitly requests.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: [Final Verification] | Blocked By: [5, 7]

  **References**:
  - Pattern: `frontend/src/pages/Relationships.tsx` - current relationship management UI.
  - Pattern: `frontend/src/pages/RelationshipGraph.tsx` - graph detail behavior if applicable.
  - Pattern: `frontend/src/services/api.ts` - relationship and sync API access.
  - Pattern: `backend/app/api/relationships.py` - relationship data contract.
  - Pattern: `backend/app/api/sync.py` - pending candidate contract from Task 3.

  **Acceptance Criteria**:
  - [ ] Relationship UI exposes source chapter/evidence/confidence/history for synced relationships.
  - [ ] Pending relationship candidates are visible and actionable through shared review UI.
  - [ ] End-to-end smoke proves accepted chapter text updates both relationship and goldfinger data.
  - [ ] End-to-end smoke proves conflicting text creates pending candidate only.
  - [ ] All verification commands pass.

  **QA Scenarios**:

  ```
  Scenario: Accepted chapter sync updates both domains
    Tool: Playwright + Bash/API smoke
    Steps: Save chapter text `林墨激活天命系统，任务是在三日内救下师姐苏青；林墨与苏青从敌对转为盟友。`; process sync; open `/project/<projectId>/goldfingers` and relationships page.
    Expected: goldfinger `天命系统` exists with task/reward/rule evidence; relationship `林墨-苏青` shows盟友/relationship summary and evidence excerpt from source chapter.
    Evidence: .sisyphus/evidence/task-8-e2e-sync.png

  Scenario: Contradiction enters pending review
    Tool: Playwright + Bash/API smoke
    Steps: Save another chapter text that contradicts goldfinger owner/status or relationship direction with low confidence; process sync; open pending review panel.
    Expected: official records remain unchanged; pending candidate displays source chapter, confidence, conflict reason, approve/reject buttons.
    Evidence: .sisyphus/evidence/task-8-conflict-pending.png
  ```

  **Commit**: YES | Message: `test(e2e): harden relationship and goldfinger sync flows` | Files: [`frontend/src/pages/Relationships.tsx`, `frontend/src/pages/RelationshipGraph.tsx`, `frontend/src/components/goldfingers/*`, `frontend/src/services/api.ts`, `frontend/src/types/index.ts`, `backend/tests/*`, `.sisyphus/evidence/*`]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.

- [ ] F1. Plan Compliance Audit — oracle
  - Verify every requested capability from the original Chinese request is implemented.
  - Verify no forbidden scope was added.
  - Verify every task’s acceptance criteria and evidence files exist.

- [ ] F2. Code Quality Review — unspecified-high
  - Review backend service boundaries, migration parity, frontend API usage, and UI component cohesion.
  - Reject if `chapters.py` contains inline AI merge logic or frontend adds an ad-hoc HTTP client.

- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
  - Execute API/browser QA scenarios from Tasks 7 and 8.
  - Capture screenshots/logs under `.sisyphus/evidence/`.
  - Reject if any scenario relies on human-only visual confirmation.

- [ ] F4. Scope Fidelity Check — deep
  - Confirm all new behavior stays within goldfinger management, relationship refactor, and正文 sync scope.
  - Confirm no new CI workflow, no generic entity-framework rewrite, no unrelated redesign.

## Commit Strategy

- Commit after each task if repository policy/user permits commits during execution.
- Commit messages:
  1. `feat(db): add goldfinger schema and sync provenance fields`
  2. `feat(api): add goldfinger management endpoints`
  3. `feat(sync): add chapter fact sync orchestration`
  4. `feat(sync): extract and merge goldfinger facts`
  5. `refactor(relationships): merge relationship facts through sync service`
  6. `feat(generation): include bounded goldfinger context`
  7. `feat(frontend): add goldfinger workspace management`
  8. `test(e2e): harden relationship and goldfinger sync flows`
- Never commit `.env`, credentials, model cache, or generated local secrets.

## Success Criteria

- User can open project workspace and see `金手指管理` beside existing entity modules.
- User can manage goldfinger type/status/tasks/rewards/rules/limits/history/import-export.
- Accepted正文 saves and generated chapter saves schedule async sync for relationships and goldfingers.
- AI-origin updates preserve evidence, source chapter, confidence, and history.
- Low-confidence/conflict records are visible as pending review and do not mutate official state until approved.
- Relationship management is more reliable and evidence-aware after refactor.
- Chapter generation receives concise approved goldfinger context.
- Backend and frontend verification commands pass with evidence saved.
