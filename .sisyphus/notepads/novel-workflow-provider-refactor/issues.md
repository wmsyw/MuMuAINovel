# Issues

## 2026-04-26 — Task 1 verification notes
- Local shell did not provide a bare `python` command until the backend virtualenv was activated; verification used `source backend/.venv/bin/activate && python -m pytest ...`, matching the acceptance command inside the venv.
- Initial frontend build after adding Vitest exposed Node timer ambient types through included test files (`Timeout` vs `number` in `sessionManager`); excluding tests from the app tsconfig fixed this without product code changes.

## 2026-04-26 — Task 1 cleanup
- Removed the out-of-scope `.gitignore` edit from Task 1 cleanup; no `backend/tests/__pycache__/` files were present after rerunning pytest, and the Task 1 backend/frontend verification suite passed again.

## 2026-04-26 — Task 2 verification environment
- The existing `backend/.venv` points to Python 3.14; installing the full pinned `requirements.txt` there fails on `torch==2.8.0` because no compatible Python 3.14 wheel is available. Task 2 verification used a temporary Python 3.11 venv with the minimal test dependencies (`pytest`, `sqlalchemy`, `alembic`, `pydantic`, `pydantic-settings`, `fastapi`) and ran the acceptance commands as `python -m pytest` inside that venv. The temporary `.venv311` was removed after verification.
- LSP diagnostics still report environment/pre-existing basedpyright noise such as unresolved local SQLAlchemy/FastAPI imports, implicit `app.*` imports, and existing `database.py` type issues. Runtime pytest schema/migration verification passed; no additional LSP-specific code changes were made to avoid broad type-suppression churn in this schema task.

## 2026-04-26 — Task 2 Phase 1 QA cleanup
- Removed the out-of-scope Goldfinger draft/plan artifacts after confirming they existed (`.sisyphus/drafts/goldfinger-relationship-sync.md` first, then `.sisyphus/plans/goldfinger-relationship-sync.md`). Follow-up glob for `.sisyphus/**/goldfinger-relationship-sync.md` should return no files; grep for the literal name may still find this historical cleanup note.
- Resolved the migration/ORM nullability mismatch by enforcing `organization_members.organization_entity_id` as NOT NULL after backfill rather than weakening the ORM. This preserves the Task 2 split invariant that every organization membership points at a canonical `organization_entities` row.

## 2026-04-26 — Task 4 verification environment
- Task 4 verification used the same temporary `uv run --python python3.11 --with ... python -m pytest` dependency set as Task 2 because the checked-in backend virtualenv still has incompatible local dependency noise. Evidence logs were written to `.sisyphus/evidence/task-4-ai-provider-capabilities.log` and `.sisyphus/evidence/task-4-task2-compatibility.log`.
- LSP diagnostics remain dominated by the known environment/pre-existing basedpyright issues: unresolved installed packages, implicit `app.*` imports, deprecated typing-style warnings, and broad existing `ai_service.py` typing noise. Runtime pytest verification passed; no project-wide type-suppression or import-style churn was added.

## 2026-04-26 — Task 4 QA fix
- QA correctly found that `REGISTRY_PATH` pointed at `backend/data/reasoning_capabilities.json` while the real JSON file was missing from the worktree. Added the file under `backend/data/` with representative OpenAI, Claude, Gemini 3, and Gemini 2.5 mappings, and strengthened `tests/test_ai_provider_capabilities.py` to assert all four provider/model families plus preflight rejection for unsupported explicit intensities.
- Removed the reintroduced `.sisyphus/plans/goldfinger-relationship-sync.md` artifact. Follow-up glob for `.sisyphus/**/goldfinger-relationship-sync.md` returned no files; grep still finds only historical notepad text mentioning the cleanup.
- Removed the broad `# pyright: reportAny=false, reportUnknownMemberType=false` suppression from the Task 4 test file; remaining LSP output is environment/pre-existing noise (`pytest` unresolved and implicit `app.*` imports), while the exact uv pytest verification commands pass and append to the Task 4 evidence logs.

## 2026-04-26 — Task 4 registry retry
- Atlas still could not see `backend/data/reasoning_capabilities.json` because root `.gitignore` ignored `data/` directories broadly, so the registry existed locally but was hidden from `Glob`/`git status`. Added explicit `.gitignore` exceptions for `backend/data/` and `backend/data/reasoning_capabilities.json`; `Glob(backend, "**/reasoning_capabilities.json")` now returns the concrete registry file and `git status --short` now shows `?? backend/data/` for the untracked registry directory.
- Re-ran the exact Task 4 capability pytest command after the ignore fix; output was appended to `.sisyphus/evidence/task-4-ai-provider-capabilities.log` and passed with `6 passed`.

## 2026-04-26 — Task 3 verification environment
- Bare `python -m pytest tests/test_legacy_backfill.py` still fails in this shell because `python` is not on PATH; that stderr was appended to `.sisyphus/evidence/task-3-backfill-error.log` before using the same temporary `uv run --python python3.11 --with ... python -m pytest ...` pattern from Tasks 2/4.
- LSP diagnostics on the changed backend files remain dominated by known local environment noise (`sqlalchemy` unresolved and implicit `app.*` imports). One concrete local optional-member issue in `_join_text` was fixed; runtime pytest verification passed after the fix.

## 2026-04-26 — Task 5 verification environment
- Task 5 verification used `uv run --python python3.11 --with ... python -m pytest ...` for the two required pytest commands, matching the Task 2/4 workaround for the local Python environment. Outputs were appended to `.sisyphus/evidence/task-5-openai-responses.log` and `.sisyphus/evidence/task-5-openai-compat.log`.
- LSP diagnostics on the changed OpenAI files still show the project-wide basedpyright environment/style noise noted in prior tasks (`app.*` implicit imports, deprecated `typing` aliases, existing async-generator override signatures, and Any/Dict strictness). Runtime pytest verification passed for both Task 5 suites.

## 2026-04-26 — Task 6 verification environment
- Task 6 verification used the established `uv run --python python3.11 --with ... python -m pytest ...` command because the checked-in backend environment remains unsuitable for bare Python verification. Extraction and compatibility pytest outputs were appended to `.sisyphus/evidence/task-6-extraction-core.log`; the malformed-output focused pytest output was appended to `.sisyphus/evidence/task-6-extraction-core-error.log`.
- LSP diagnostics on the changed extraction service/test files still report the known local basedpyright environment/import noise (`sqlalchemy` unresolved and implicit `app.*` imports). Concrete new service diagnostics from optional aliases/payload typing were fixed before final pytest rerun; runtime verification passed.

## 2026-04-26 — Task 7 verification environment
- Task 7 verification used the established `uv run --python python3.11 --with ... python -m pytest ...` command because the checked-in backend virtualenv remains incompatible with the pinned dependency set. Targeted and compatibility outputs were appended to `.sisyphus/evidence/task-7-merge-timeline.log`; edge/failure-case focused tests were appended to `.sisyphus/evidence/task-7-merge-timeline-error.log`.
- LSP diagnostics on the changed Task 7 files still show the known local basedpyright environment/import noise (`sqlalchemy` unresolved, implicit `app.*` imports, and SQLAlchemy model attributes typed as unknown). A concrete optional `TimelinePoint | None` diagnostic and local unused-call-result warnings were fixed; runtime pytest verification passed.

## 2026-04-26 — Task 8 verification environment
- Task 8 verification used the established `uv run --python python3.11 --with ... python -m pytest ...` command. Targeted and compatibility pytest outputs were appended to `.sisyphus/evidence/task-8-world-results.log`; rollback-focused output was appended to `.sisyphus/evidence/task-8-world-results-error.log`.
- LSP diagnostics on the changed Task 8 files still show the known local basedpyright environment/import and SQLAlchemy unknown-member noise (`sqlalchemy` unresolved, implicit `app.*` imports). Runtime pytest verification passed after fixing the concrete unused-call-result test warning.

## 2026-04-26 — Task 8 QA rollback status fix
- Atlas found the Task 8 world-result service/test used a `rolled_back` status that was outside the planned world-result vocabulary. Rollback now marks the current accepted `WorldSettingResult` as `superseded`, reactivates the prior snapshot as `accepted`, and repeated rollback remains idempotent; targeted, rollback-focused, and compatibility pytest reruns passed with output appended to the Task 8 evidence logs.

## 2026-04-26 — Task 9 verification environment
- Task 9 verification used the established `uv run --python python3.11 --with ... python -m pytest ...` command. Targeted policy and completed-task compatibility outputs were appended to `.sisyphus/evidence/task-9-policy-gate.log`; focused blocked/admin/advanced override output was appended to `.sisyphus/evidence/task-9-policy-gate-error.log`.
- LSP diagnostics on changed backend files still show the known local basedpyright environment/import noise (`sqlalchemy`/`fastapi` unresolved and implicit `app.*` imports). Concrete new literal typing diagnostics in `tests/test_entity_generation_policy.py` were fixed before the final targeted pytest rerun.

## 2026-04-26 — Task 9 QA book-import bypass fix
- QA found `backend/app/services/book_import_service.py` still bypassed the central entity generation policy by creating AI careers, characters, organizations, relationships, and organization members during拆书导入 post-import generation. The fix gates career and character/organization helpers before prompt/AI calls and returns deterministic zero-created blocked behavior for ordinary users.
- Regression tests avoid greenlet-dependent async SQLAlchemy by using a tiny async facade over a sync in-memory session; this preserves the required uv dependency set while still exercising the async book-import helper policy branches. Targeted Task 9 tests now pass with `7 passed`; focused book-import policy tests pass with `2 passed`; compatibility suite remains `40 passed`.

## 2026-04-26 — Task 9 QA typing fix
- Atlas Phase 2 found new `object` attribute-access diagnostics in `tests/test_entity_generation_policy.py` from the local `AsyncSessionAdapter.execute()` helper. Added narrow local `Protocol` return types plus explicit casts for the book-import audit/career scalar result lists, with no suppressions or runtime behavior changes. Targeted Task 9 pytest remains `7 passed`.

## 2026-04-27 — Task 10a verification environment
- Task 10a verification used the established `uv run --python python3.11 --with ... python -m pytest ...` command. Targeted extraction API output and compatibility runs were appended to `.sisyphus/evidence/task-10a-extraction-api.log`; focused invalid-merge/rollback edge output was appended to `.sisyphus/evidence/task-10a-extraction-api-edge.log`.
- Initial API test collection exposed that importing `app.main` under the minimal uv dependency set needs local stubs for MCP, memory, and email services; the tests now stub only those heavy imports while still asserting the real extraction router is registered in `main.py` and OpenAPI includes `/api/extraction/*` paths.
- LSP diagnostics on changed backend files remain dominated by known local environment/import noise (`fastapi`/`sqlalchemy`/`pydantic`/`pytest` unresolved and implicit `app.*` import warnings). Concrete new attribute-assignment and unused-call-result issues in the Task 10a files were cleaned up before the final targeted pytest rerun passed.

## 2026-04-27 — Task 10a QA typing cleanup
- Cleaned `backend/tests/test_extraction_api.py` by adding narrow local result/session `Protocol`s and `TypeVar`-based `run_sync` typing, assigning intentional `sys.modules.setdefault(...)` results, and keeping test/API semantics unchanged. Targeted verification passed with `uv run --python python3.11 ... python -m pytest tests/test_extraction_api.py -q` (`5 passed, 4 warnings`); grep found no `type: ignore`, `pyright`, `TODO`, `FIXME`, or `HACK`, and the Goldfinger artifact glob remained empty.

## 2026-04-27 — Task 10b verification environment
- Task 10b verification used the established minimal uv Python 3.11 dependency command because the checked-in backend environment remains unsuitable for bare pytest. The required targeted command passed with `8 passed, 4 warnings`; focused timeline and world-result QA outputs were appended to `.sisyphus/evidence/task-10b-timeline-api.log` and `.sisyphus/evidence/task-10b-world-api.log`.
- LSP diagnostics on changed Task 10b files still show the known local basedpyright environment/import noise (`fastapi`/`sqlalchemy`/`pydantic`/`pytest` unresolved and implicit `app.*` import warnings). No broad suppressions were added; runtime API verification and OpenAPI generation passed.

## 2026-04-27 — Task 10b QA world-result status fix
- Atlas Phase 1 found the Task 10b world-setting API schema had reintroduced `rolled_back` into `WorldSettingResultStatus`, contradicting the Task 8 rollback decision. Narrowed the API status enum back to `pending | accepted | rejected | superseded` and added OpenAPI regression coverage while preserving rollback behavior (`current=superseded`, previous=`accepted`). Targeted Task 10b verification passed again with `8 passed, 4 warnings`, with output appended to `.sisyphus/evidence/task-10b-world-api.log`.

## 2026-04-27 — Task 11 verification environment
- Task 11 verification used the established minimal uv Python 3.11 dependency command. Targeted trigger verification passed with `6 passed`; extraction pipeline/API compatibility was also rerun and appended to `.sisyphus/evidence/task-11-triggers.log` / `task-11-triggers-error.log`.
- LSP diagnostics on changed backend files remain dominated by known local basedpyright environment/import noise (`fastapi`/`sqlalchemy`/`pydantic` unresolved and implicit `app.*` import warnings). Concrete new argument-type/unused-call-result issues in Task 11 edits were fixed before the final targeted pytest rerun.
- Follow-up glob for `.sisyphus/**/goldfinger-relationship-sync.md` returned no files; `.sisyphus/boulder.json` remains unrelated untracked orchestration state and was not staged or committed.

## 2026-04-27 — Task 12 verification environment
- Bare `python -m pytest tests/test_entity_api_compatibility.py tests/test_profession_timeline_api.py` is still unavailable in this shell (`zsh: command not found: python`), so verification used the established `uv run --python python3.11 --with ... python -m pytest ...` fallback. Output was appended to `.sisyphus/evidence/task-12-entity-api.log`; the bare-python failure was appended to `.sisyphus/evidence/task-12-entity-api-error.log`.
- Targeted Task 12 verification passed with `4 passed, 4 warnings`. LSP diagnostics on changed files remain dominated by the known local environment/import noise (`fastapi`/`sqlalchemy`/`pydantic`/`pytest` unresolved, implicit `app.*` imports, SQLAlchemy unknown members); runtime pytest is the reliable gate for this task.
- Follow-up glob for `.sisyphus/**/goldfinger-relationship-sync.md` returned no files before editing, and `.sisyphus/boulder.json` remained untouched.

## 2026-04-27 — Task 12 QA export/enrichment fix
- Atlas QA found character export still validated only `Character.id`, so canonical organization IDs from the updated list/detail compatibility layer could 404. The route now resolves normal characters plus canonical/bridge/legacy organization IDs, verifies project ownership for each, and emits the legacy export contract (`version`, `export_type`, `count`, `data`) with canonical organizations represented as `is_organization: true`.
- `GET /api/organizations/{org_id}` now accepts the same explicit enrichment flags as the organization list; default detail responses remain old `OrganizationResponse`-compatible, while requested metadata is additive. Targeted Task 12 pytest rerun passed with `4 passed, 4 warnings`; forbidden-marker grep found no new `TODO`/`FIXME`/`HACK`/suppression markers, and the Goldfinger artifact glob remained empty.

## 2026-04-27 — Task 13 verification notes
- Initial frontend lint failed because `Settings.tsx` exported test helpers directly, triggering `react-refresh/only-export-components`; helpers now remain file-local and are exposed only as a static `__testUtils` property on the default Settings component for Vitest coverage.
- `npm run build` still emits the known Vite chunk-size warnings and writes built assets to `backend/static` per the existing frontend build configuration; targeted Settings tests, build, and lint all passed after the lint fix.
- Follow-up glob for `.sisyphus/**/goldfinger-relationship-sync.md` returned no files; no new Goldfinger artifact was created.

## 2026-04-27 — Task 14 verification notes
- `npm run test -- --run extraction`, `npm run build`, and `npm run lint` were run from `frontend/`; stdout was appended to `.sisyphus/evidence/task-14-entity-review-ui.log` and stderr/warnings to `.sisyphus/evidence/task-14-entity-review-ui-error.log`.
- `npm run build` continues to write the configured Vite output under `backend/static` and may emit the known large chunk warnings; no backend code changes were needed for Task 14.
- Follow-up glob for `.sisyphus/**/goldfinger-relationship-sync.md` returned no files; `.sisyphus/boulder.json` was not edited.
- Initial verification surfaced an SSR-only test assertion gap and a build callback return-type mismatch; after fixing them, the final appended frontend verification block passed with extraction tests `3 passed`, Vite build success, and lint success.

## 2026-04-27 — Task 14 QA accept-path test fix
- Atlas QA required the candidate accept scenario to exercise the actual `ExtractionCandidateReviewPanel` component path. The extraction review test now renders the panel with jsdom/ReactDOM, clicks the visible `接受入库` button, verifies the injected API client's `acceptCandidate` and `listCandidates` mocks are called, verifies the canonical refresh callback runs, and asserts the tab counts update to `正文发现 (0)` / `已拒绝/历史 (1)` after the mocked accepted candidate refresh.
- The first QA-fix test run exposed that confidence was not visibly labeled as `置信度 87%`; the panel now renders an explicit small confidence label next to the AntD progress bar. Final required frontend verification passed, forbidden-marker grep on the touched component/test files found no matches, and the Goldfinger artifact glob remained empty.
