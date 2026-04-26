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
