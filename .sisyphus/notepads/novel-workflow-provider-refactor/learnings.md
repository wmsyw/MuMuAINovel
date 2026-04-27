# Learnings

## 2026-04-26 — Task 1 minimal harness
- Backend tests are runnable from `backend/` with package-style imports under `backend/tests/`; keeping `tests/__init__.py` and relative imports avoids basedpyright implicit-relative-import diagnostics.
- Golden fixture validation now treats evidence text, confidence, chapter/order, and exact source offsets as mandatory for every expected assertion; future extraction tests can reuse `tests.fixture_schema.load_golden_fixture()`.
- Frontend Vitest can stay minimal by testing `src/store/eventBus.ts` directly; no Testing Library or browser automation dependency is required for this first smoke/contract harness.
- Build typechecking includes `src` by default, so `tsconfig.app.json` excludes `*.test.ts(x)` to prevent Vitest/Node ambient types from changing production `tsc -b` behavior.

## 2026-04-26 — Task 2 schema correction
- Task 2 requires a hard schema split, not transitional compatibility: final ORM/migration contracts remove `characters.is_organization`, `organization_type`, `organization_purpose`, and `organization_members`, migrate old organization-character rows into `organization_entities`, and delete those old org rows from `characters` only after data is copied.
- `organization_entities` is the canonical org table and must absorb both old `Character` org fields (`personality`, `background`, `status`, `current_state`, `avatar_url`, `traits`, org type/purpose) and old `organizations` detail fields (`parent_org_id`, `level`, `power_level`, `member_count`, `location`, `motto`, `color`).
- Relationship migration needs a typed endpoint table (`entity_relationships`) so old relationships involving organization-character rows can be preserved as `organization` endpoints after org rows are removed from `characters`.
- `ExtractionCandidate` contract uses `canonical_target_type`/`canonical_target_id`, not `canonical_entity_type`; tests now assert the old names are absent and timeline/rollback fields exist.
- Phase 1 QA nullability correction: keep `OrganizationMember.organization_entity_id` required in final schema. Migrations add it nullable for safe backfill, populate it from legacy `organizations`, then enforce `nullable=False` (`op.alter_column` in Postgres, `batch_alter_table(...).alter_column` in SQLite). Tests now assert the final upgraded SQLite schema and ORM metadata are both non-null.

## 2026-04-26 — Task 4 reasoning capability registry
- Provider/model reasoning support is centralized in `backend/data/reasoning_capabilities.json`; service code should call `build_reasoning_config()` rather than branching on provider/model names.
- Normalized reasoning intensities are exactly `auto`, `off`, `low`, `medium`, `high`, `maximum`; explicit unsupported selections raise `UnsupportedReasoningIntensityError`, while unknown models warn and resolve to `auto` with an empty provider payload.
- `AIService` now stores `default_reasoning_intensity` and JSON `reasoning_overrides`, resolves the config before provider dispatch, and passes `reasoning_config` through provider interfaces without changing client HTTP payloads in this task.
- Settings schema/API now expose reasoning defaults and `/settings/reasoning-capabilities` metadata; frontend should continue storing normalized intensities, not provider-native payloads.

## 2026-04-26 — Task 3 legacy backfill
- Legacy provenance backfill is implemented as a sync SQLAlchemy service (`backend/app/services/legacy_backfill_service.py`) so the in-memory SQLite migration-style harness can call it directly without async DB/session or API setup.
- Backfill idempotency is enforced by selecting existing provenance by `(project_id, entity_type, entity_id, source_type, source_id, claim_type)`, aliases by active normalized alias/entity, timeline events by legacy relationship/member/career keys with null valid chapter bounds, and world results by accepted `legacy_existing_record` project snapshot.
- The service intentionally creates no `extraction_runs` or candidates; preserved records receive `entity_provenance.source_type = legacy_existing_record`, `confidence = 1.0`, and null run/candidate/chapter fields.

## 2026-04-26 — Task 5 OpenAI Responses adapter
- `OpenAIClient` now keeps Chat Completions methods intact and adds `/responses` methods on the same `BaseAIClient` HTTP/retry/semaphore path; Responses tools are converted from the existing nested Chat function-tool shape by flattening `function.name/description/parameters` and stripping `$schema`.
- OpenAI Responses normalization maps `output` message text and `function_call` items into the existing provider shape (`content`, `tool_calls`, `finish_reason`, `usage`) plus additive `provider_metadata` and `reasoning_continuation` fields for response IDs/status/reasoning continuation data.
- `OpenAIProvider` chooses Responses from the Task 4 `ReasoningConfig.provider_payload`/`provider_native` marker rather than model-name branches; empty or `off`/`none` reasoning payloads continue to use legacy `/chat/completions` for compatibility.

## 2026-04-26 — Task 6 extraction core
- `backend/app/services/extraction_service.py` is a sync SQLAlchemy service by design so in-memory SQLite tests can call it directly; it reads only persisted `Chapter.content`, creates one `ExtractionRun`, validates all model candidates before adding any rows, then stages only pending `ExtractionCandidate` rows.
- Extraction dedupe is keyed by project, chapter, SHA-256 content hash, schema version, and prompt hash, and only reuses completed runs; `force=True` creates an additional completed run/candidate set without deleting previous rows.
- Candidate validation requires supported type, confidence in `[0,1]`, source order/offsets, chapter ID/number consistency when provided, and exact evidence text matching the persisted chapter content span. Normalized names/aliases are stored in candidate payloads, not canonical alias rows.
- Malformed/non-JSON extractor output is recorded as a failed run with error details and raw response snapshot; no candidates, canonical entities, provenance, timeline events, or world-setting results are created.

## 2026-04-26 — Task 7 merge/timeline service
- Canonical merge is implemented as sync SQLAlchemy services (`candidate_merge_service.py` and `timeline_projection_service.py`) so existing in-memory SQLite backend tests can exercise accept/merge/reject/rollback/projection without routers or async session setup.
- Entity candidate idempotency follows Task 3 patterns: provenance is keyed by extraction candidate/source/entity/claim, aliases are keyed by active normalized alias/entity, and repeated accepted/merged operations do not duplicate `Character`, `OrganizationEntity`, `Career`, `EntityProvenance`, or `EntityAlias` rows.
- Safe auto-merge is intentionally narrow: only high-confidence entity candidates (`>= 0.92`) with exactly one same-type normalized name/alias match are merged; duplicate names and cross-type-only matches remain `pending` with no canonical mutation.
- Relationship, organization-affiliation, and profession-assignment candidates append `RelationshipTimelineEvent` rows and close prior active intervals by setting `valid_to_*` bounds; projection reads chapter/order coordinates and returns current state while preserving history rows.
- Rollback marks accepted candidates `superseded`, provenance `rolled_back`, timeline events `rolled_back`, and candidate-created aliases `retired`; canonical rows are never hard-deleted.

## 2026-04-26 — Task 8 world result versioning
- World-setting versioning is centralized in `backend/app/services/world_setting_result_service.py`; pending generated rows store provider/model/reasoning/prompt/raw metadata and intentionally leave `Project.world_*` unchanged until explicit accept.
- Accepting a `WorldSettingResult` updates `Project.world_time_period`, `world_location`, `world_atmosphere`, and `world_rules`, records `accepted_at`/`accepted_by`, and marks the prior accepted result `superseded` rather than deleting it.
- Rollback re-applies the most recent prior accepted/superseded result with `accepted_at` populated, marks the current accepted row `rolled_back`, and keeps legacy `legacy_existing_record` world rows usable as rollback targets.

## 2026-04-26 — Task 9 entity generation policy gate
- AI canonical entity creation is now centralized in `backend/app/services/entity_generation_policy_service.py`; ordinary AI/auto-create/candidate-promotion actions default to `candidate_only`, while `manual_create` and `manual_edit` remain explicitly allowed without override.
- Override audit uses existing `EntityProvenance` rows with `source_type="ai_generation_policy_override"` and JSON `claim_payload` carrying actor, project, entity type, endpoint/source, action, provider/model, reason, override source, and resulting canonical IDs, avoiding a new schema migration.
- Known legacy AI generation paths are gated before model/database mutation: character/organization/career SSE routes, wizard career/character generators, outline-driven auto character/org services, and the career parse/save helper. Blocked paths return deterministic policy payloads/events and do not insert canonical `Character`, `OrganizationEntity`, or `Career` rows.
- QA fix added the same policy gate to拆书导入 post-import wizard helpers before AI calls: `_generate_career_system_from_project()` now blocks/permits career generation with audit, and `_generate_characters_and_organizations_from_project()` independently evaluates character and organization policy before creating legacy canonical rows/relationships.

## 2026-04-27 — Task 10a extraction review API
- Extraction review endpoints now live in `backend/app/api/extraction.py` with the standard router prefix pattern (`/extraction` mounted under `/api` in `main.py`) and delegate accept/reject/merge/rollback behavior to the sync `CandidateMergeService` via `AsyncSession.run_sync`.
- API schemas in `backend/app/schemas/extraction.py` keep deterministic status vocabularies for runs (`pending/running/completed/failed/cancelled`) and candidates (`pending/accepted/rejected/merged/superseded`), and candidate list filtering supports `status`, query alias `type`, `chapter_id`, `run_id`, and `canonical_target` (`none`, `target_id`, or `type:target_id`).
- Focused API tests use a small sync-session async facade plus module stubs for heavy app-level services so `app.main` router registration and OpenAPI generation can be exercised under the established minimal uv dependency set without installing MCP/Chroma/email extras.

## 2026-04-27 — Task 10b timeline/world APIs
- Timeline query endpoints now live in `backend/app/api/timeline.py` with router prefix `/timeline` mounted under `/api`; handlers resolve `chapter_id`/`chapter_number`/`chapter_order`, verify project ownership through `request.state.user_id`, and delegate projections/history to `TimelineProjectionService` via `AsyncSession.run_sync`.
- Timeline response schemas in `backend/app/schemas/timeline.py` expose stable categorized state (`relationships`, `affiliations`, `professions`) plus history rows with relationship/profession/organization identifiers and chapter validity bounds, matching the Task 7 append-only event model.
- World-setting result endpoints now live in `backend/app/api/world_setting_results.py` with router prefix `/world-setting-results` mounted under `/api`; list/get/action handlers verify ownership and delegate accept/reject/rollback to `WorldSettingResultService` rather than mutating `Project.world_*` directly.
- World-setting operation responses include the reviewed result, optional previous result, and `active_world` snapshot so frontend/API consumers can refresh active world state after accept/reject/rollback without inspecting raw database rows.

## 2026-04-27 — Task 11 extraction triggers
- Automatic extraction trigger orchestration now lives in `ExtractionTriggerService` plus async post-commit helpers in `backend/app/services/extraction_service.py`; route/import code calls these only after chapter/import/generation text has committed so failed extraction cannot roll back persisted正文.
- Automatic trigger sources are stable strings: `chapter_save`, `chapter_generation`, and `book_import`; unchanged content reuses the completed run through the Task 6 content hash/prompt hash dedupe path, while changed chapter content supersedes prior pending candidates for that chapter.
- Manual re-extract actions are exposed under `/api/extraction/reextract/project`, `/api/extraction/reextract/chapter`, and `/api/extraction/reextract/range`; they force new runs and avoid canonical deletion/supersession side effects.
- `CharacterStateUpdateService` now routes analysis-derived state/relationship/organization changes into extraction candidates when `EXTRACTION_PIPELINE_ENABLED=True`, including high-confidence `auto_accept` survival-status character-state candidates; disabled mode preserves the legacy direct-mutation path.

## 2026-04-27 — Task 12 entity API compatibility
- Character compatibility routes now synthesize legacy character-shaped organization rows from canonical `OrganizationEntity` records, while normal characters remain backed by `Character`; old `/characters`, `/characters/project/{project_id}`, `/characters/{id}`, manual create/edit/delete paths remain usable without reintroducing organization columns on `characters`.
- Organization compatibility routes resolve either bridge `Organization.id`, canonical `OrganizationEntity.id`, or legacy character/organization IDs and return old `OrganizationResponse`/detail shapes from canonical organization fields; organization members now write both legacy `organization_id` bridge and required `organization_entity_id`.
- Optional enrichment flags (`include_provenance`, `include_aliases`, `include_candidate_counts`, `include_timeline`, `include_policy_status`) add provenance/alias/candidate/timeline/policy metadata only when explicitly requested; default responses intentionally omit those extraction internals.
- Career/profession APIs keep `Career` as the profession taxonomy and append `RelationshipTimelineEvent(event_type="profession")` rows for direct main/sub/stage assignment routes, allowing chapter-specific profession projections through the existing timeline service/API.

## 2026-04-27 — Task 13 Settings reasoning UI
- Frontend settings now consumes `/settings/reasoning-capabilities` and keeps the UI state normalized to `default_reasoning_intensity` (`auto/off/low/medium/high/maximum`); provider-native payload names are displayed only as backend metadata and are not submitted as frontend state.
- Settings capability matching mirrors backend behavior for wildcard model patterns and the `mumu -> openai` provider alias, disabling unsupported intensities and preflighting unsupported current/preset selections before save/test calls.
- The entity-generation override is a backend-backed `allow_ai_entity_generation` form field, normalized to default `false`, with the required warning copy preserved exactly in the Settings page and tests.

## 2026-04-27 — Task 14 entity review UI
- Frontend extraction review UI now uses shared `extractionApi`, `organizationApi`, `careerApi`, and `timelineApi` wrappers in `frontend/src/services/api.ts`; new work should continue routing candidate accept/reject/merge/rollback through those wrappers rather than page-local transport.
- `ExtractionCandidateReviewPanel` centralizes the restrained AntD review surface: outer tabs are `已入库`, `正文发现`, `待合并`, and `已拒绝/历史`; candidates are split client-side by pending status plus `canonical_target_id` because the current list API does not expose an explicit "has target" filter.
- AI canonical entity generation controls on Characters and Careers now default hidden behind the backend-backed `allow_ai_entity_generation` setting, while manual create/edit controls remain visible; the shared policy copy is kept in the review component test utils for regression coverage.
- Careers adds a `职业时间线` tab backed by `/api/timeline/projects/{project_id}/history?event_type=profession`, mapped to current character/career names when available while preserving the existing taxonomy CRUD tabs.

## 2026-04-27 — Task 15 world/inspiration draft review UI
- Frontend world-setting result review now uses shared `worldSettingResultApi` wrappers in `frontend/src/services/api.ts`; accept/reject/rollback calls return `active_world`, and the page updates `useStore().currentProject` from that snapshot rather than inferring changes from raw result rows.
- `WorldSetting.tsx` separates `当前生效世界观` manual snapshot editing from `AI结果评审`; the AI regenerate stream is treated as a result/page draft and no longer calls `projectApi.updateProject` from the AI preview path.
- `WorldSetting` exposes focused test utilities for snapshot application and action orchestration; the jsdom test renders the page, clicks `接受结果`, and verifies the mocked result API updates the active project world fields.
- `Inspiration.tsx` keeps generated ideas as drafts by default: users can save local inspiration drafts or create a project draft through `projectApi.createProject`; the full `AIProjectGenerator` handoff remains an explicit secondary option.

## 2026-04-27 — Task 16 timeline UI/query surfaces
- `TimelineReviewPanel` now centralizes the restrained AntD timeline query surface: chapter/order filters call `timelineApi.getProjectState`, history calls `timelineApi.getProjectHistory`, and the same table renders evidence, confidence, source offsets, validity range, status, and supersession metadata.
- Characters, Organizations, and Careers integrate timeline panels as extra tabs inside the existing `ExtractionCandidateReviewPanel`; no route or graph surface was added, and manual CRUD/review tabs remain intact.
- Current projection and history intentionally interpret validity differently: current rows from `/state` stay labeled `生效中`, while history rows with `valid_to_*` render ended semantics so closed relationships remain auditable after they disappear from current projection.

## Task 17: Cleanup and Documentation
- Static audit tests using Python's `ast` module are effective for verifying call ordering and argument presence without running the full application.
- Centralizing policy evaluation in services (`AutoCharacterService`, `AutoOrganizationService`) ensures that all entry points (API, background tasks) are protected.
- Documentation should explicitly cover feature flags and migration paths to manage user expectations during major refactors.
