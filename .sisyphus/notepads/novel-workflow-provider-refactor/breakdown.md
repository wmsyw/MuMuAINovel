# Granular Implementation Breakdown

## Task 1 — Test harness and golden fixtures
- Backend: add pytest dependency/config in `backend/requirements.txt` and test conventions under `backend/tests/`; verify `cd backend && python -m pytest tests/test_harness_smoke.py`.
- Fixtures: create Chinese prose fixture files under `backend/tests/fixtures/**` covering aliases, org affiliation change, profession change, relationship timeline, world fact, duplicate name, contradictory evidence; verify `tests/test_golden_fixtures.py`.
- Validation: add malformed fixture tests requiring source spans, evidence, confidence; verify `tests/test_golden_fixture_validation.py`.
- Frontend: add Vitest config and `test` script in `frontend/package.json`; add smoke/contract tests; verify `cd frontend && npm run test -- --run && npm run build && npm run lint`.
- Evidence: capture `.sisyphus/evidence/task-1-*` logs.

## Task 2 — Schema, migrations, org split
- Models: add first-class `OrganizationEntity` and remove future dependency on `Character.is_organization`; preserve org-specific fields.
- Models: add `ExtractionRun`, `ExtractionCandidate`, `EntityAlias`, `EntityProvenance`, `RelationshipTimelineEvent`, `WorldSettingResult` with required provenance/status/timeline fields and indexes.
- Settings/config: add `default_reasoning_intensity`, `reasoning_overrides`, `allow_ai_entity_generation`, and `EXTRACTION_PIPELINE_ENABLED=false` default.
- Migrations: add mirrored SQLite/PostgreSQL Alembic migrations for org split, extraction graph, world results, timeline, settings columns.
- Tests: add migration/schema/parity tests proving fresh schema, org data preservation, settings columns, and both migration trees align.

## Task 3 — Legacy backfill
- Service: create idempotent backfill service for existing characters, orgs, careers/professions, relationships, and `Project.world_*`.
- Provenance: create legacy aliases/provenance rows with source type `legacy_existing_record`, no AI/network calls, and no destructive edits.
- Timeline/world: create initial timeline events and accepted legacy world-setting result rows.
- Tests: verify preservation, editability, no duplicate rows after two backfill runs.

## Task 4 — Provider reasoning capability registry
- Registry: add data-driven capability file/table with provider, model pattern, supported intensities, mappings, defaults, last verified date, notes.
- Types/service: add normalized enum `auto|off|low|medium|high|maximum`, `NormalizedReasoningConfig`, registry lookup, preflight validation, unknown-model auto fallback.
- Providers: extend `BaseAIProvider.generate()` and `generate_stream()` plus implementations with optional `reasoning_config`.
- API/schema: expose normalized settings/capability metadata through settings schema/API.
- Tests: cover OpenAI, Claude, Gemini 2.5/Gemini 3 supported/unsupported mappings and preflight-before-HTTP behavior.

## Task 5 — OpenAI Responses adapter
- Client: add `OpenAIClient.create_response()` and `create_response_stream()` alongside existing chat completions using same HTTP client/base URL/API key.
- Provider: route `OpenAIProvider` through capability registry; use `/responses` when appropriate and chat completions otherwise.
- Normalization: map Responses output, streaming events, tool calls, usage, finish status, provider metadata, continuation metadata into existing internal shape.
- Tests: add Responses adapter and chat compatibility tests; assert no separate Responses client class.

## Task 6 — Extraction core service
- Service: create `backend/app/services/extraction_service.py` to read persisted chapter text and create extraction runs/candidates only.
- Prompt/schema: define structured output for character, organization, profession, relationship, affiliation, profession assignment, world fact, character state.
- Validation/dedupe: require normalized names, aliases, confidence, evidence, chapter/order, source offsets, raw payload, pending status; dedupe by project/chapter hash/schema/prompt unless `force=true`.
- Fail-safe: malformed AI JSON marks run failed with error and no canonical mutation.
- Tests: use golden prose to assert candidates/source offsets and unchanged rerun behavior.

## Task 7 — Canonical merge, dedupe, rollback, timeline projection
- Service: implement accept/reject/merge/supersede/rollback operations with audit and idempotency.
- Auto-merge: allow only confidence >= 0.92, same type, single normalized alias match, and no active conflicting timeline claim.
- Provenance: create aliases/provenance per accepted claim without hard deleting referenced history.
- Timeline: append relationship/profession/org affiliation events and query chapter/order current projections.
- Tests: acceptance/projection, ambiguous no-auto-merge, chapter 3/6/10 state, rollback/supersession.

## Task 8 — World-setting result versioning
- Service: generate pending `WorldSettingResult` rows with project/provider/model/reasoning/prompt/raw/status metadata.
- Accept/reject: accepting updates active `Project.world_*` snapshot with audit; rejecting leaves snapshot unchanged.
- Rollback: supersede current result and re-apply previous accepted snapshot without deleting history.
- Integration: route existing world regeneration to pending results.
- Tests: pending generation no overwrite, accept updates, rollback restores prior accepted result.

## Task 9 — Entity generation policy gate
- Service: add central backend policy service for AI character/org/profession generation with default candidate-only/no-canonical behavior.
- Audit: add override audit metadata for actor, project, endpoint/source, type, provider/model, reason, timestamp, resulting canonical IDs.
- Call sites: gate `characters.py`, `organizations.py`, `careers.py`, `wizard_stream.py`, `outlines.py`, auto-character/org services.
- Manual edits: preserve manual create/edit without override.
- Tests: ordinary blocked/candidate-only, admin override audited, all known call sites use policy service.

## Task 10a — Extraction candidate/review APIs
- Schemas: add run/candidate/review request/response schemas with deterministic statuses.
- Router: expose list/get runs, filter candidates, accept/reject/merge, rollback under `/api`; register in `main.py`.
- Boundaries: keep business logic in services, not router functions.
- Tests: router registration, stable JSON, failed merge structured errors without canonical mutation, OpenAPI generation.

## Task 10b — Timeline/world-result APIs
- Timeline API: list/query timeline relationships/professions/affiliations by project and optional chapter/order.
- World API: list/get/accept/reject/rollback world-setting results.
- Router registration: add to `main.py` with existing `/api` conventions and thin handlers.
- Tests: timeline chapter state, world accept/rollback, OpenAPI generation.

## Task 11 — Automatic/manual extraction triggers
- Feature flag: all triggers skip when `EXTRACTION_PIPELINE_ENABLED=false` and preserve legacy behavior.
- Persistence hooks: trigger after chapter save/update, generated chapter persistence, and TXT import apply completion.
- Wrapper: when flag enabled, wrap `CharacterStateUpdateService` direct mutations into extraction candidates; when disabled preserve original behavior.
- Manual re-extract: add project-wide/chapter/range modes with force/new run behavior and no automatic canonical deletion.
- Tests: one run for changed content, unchanged dedupe, failed extraction preserves text, manual modes create runs.

## Task 12 — Entity API compatibility
- Characters/orgs/careers: keep existing CRUD/list/edit/delete defaults while optionally exposing provenance, aliases, candidate counts, timeline summaries.
- Policy: ensure AI generation endpoints behave consistently with Task 9 across all entity types.
- Professions: treat careers as canonical profession taxonomy; profession assignments are timeline relationships.
- Tests: old response shape works, manual edits work, optional query flag adds summaries, profession timeline by chapter.

## Task 13 — Frontend settings UI/API
- Types/API: extend `frontend/src/types/index.ts` and `frontend/src/services/api.ts` for normalized reasoning capability/settings contracts.
- UI: update `Settings.tsx` to render supported intensity options, disable/reject unsupported choices, and show backend validation errors.
- Override: add backend-backed advanced/admin toggle default off with warning copy; do not make frontend-only.
- Regression: preserve current model fetch, API test, preset, MCP flows.
- Tests: Settings vitest for OpenAI/Claude/Gemini capabilities and rejection messages; build/lint.

## Task 14 — Entity candidate review UI
- Components: add `ExtractionCandidatePanel`, `CandidateMergeDialog`, `ProvenanceDrawer`, `ManualReextractModal` or equivalent shared components.
- Pages: integrate Characters, Organizations, Careers with 已入库/正文发现/待合并/已拒绝历史 and career timeline sections.
- Policy UI: hide/disable AI generate controls unless backend says override enabled; keep manual create/edit.
- API actions: accept/reject/merge/rollback through shared wrappers; refresh canonical list/status.
- Tests: mocked candidate accept path and generation disabled by default; build/lint.

## Task 15 — Inspiration and WorldSetting draft/result UI
- Inspiration: keep generated ideas as drafts; support save as inspiration, convert to candidates, or apply to world-setting result draft only.
- WorldSetting: show versioned results, active-vs-candidate diff, statuses, provider/model/reasoning metadata, provenance links.
- Actions: accept/reject/rollback world results through API and update active snapshot from response.
- Guardrail: no silent canonical entity/world mutation.
- Tests: world accept after diff review, inspiration apply avoids canonical create endpoint; build/lint.

## Task 16 — Relationship/affiliation/profession timeline UI
- Components: add minimal timeline panels with chapter/order filter, current projection, history mode, evidence/confidence/status.
- Pages: embed timeline panels in Characters, Organizations, Careers without new graph route.
- API: use Task 10b timeline query wrappers and deterministic current-vs-history payloads.
- Tests: chapter 3/6/10 state changes and ended relationships absent from current but visible in history; build/lint.

## Task 17 — Cleanup/docs/bypass audit
- Deprecation: mark `CharacterStateUpdateService`, `auto_character_service`, and `auto_organization_service` deprecated with migration notes/safe wrappers.
- Static audit: add tests detecting ungated AI character/org/career generation bypasses and direct frontend API clients.
- Docs: update README/project docs for extraction-first workflow, triggers, override policy, migration/backfill, world result accept/rollback, reasoning settings, feature flag, commands.
- Verification: backend static audit and frontend full build/lint/test.

## Task 18 — Integrated QA/evidence
- Commands: run full backend pytest, frontend test/build/lint, docker-compose build, migration/provider/extraction/timeline/UI focused suites.
- Evidence: capture logs under `.sisyphus/evidence/` for every major command and task QA scenario.
- Fixes: delegate only failure fixes, no new product scope.
- Note: write final implementation note with deferred items limited to plan exclusions.

## Final Verification Wave
- F1: Oracle plan compliance audit verifies all acceptance criteria/evidence and user decisions.
- F2: Code quality review checks service boundaries, migrations, API contracts, provider abstractions, frontend state.
- F3: Real manual QA uses agent-controlled browser for settings, candidates, accept/merge/reject, world results, timeline; captures screenshots/logs.
- F4: Scope fidelity confirms deferred items stayed out and legacy projects/data still load.
