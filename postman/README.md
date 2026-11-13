# MigraPilot Postman API checks

1. Start the services at the project root: `docker compose up --build`.
2. Open Postman → Import: `MigraPilot-Phase1.postman_collection.json` and `MigraPilot-Local.postman_environment.json`.
3. Choose the **MigraPilot Local** environment.
4. Run the collection **in its presented order**. Registration generates a new disposable local test account and saves a JWT (`token`); project creation saves `project_id`.
5. Confirm every test passes. No external API key is required for Phase 1.

Note: `local_test_password` is a disposable DEMO account password. Never store real user credentials or production tokens in exported environments. The collection modifies (then deletes) a demo project in your local database, and the registration test creates a user. Keep it on local development only.

API base: `{{base_url}}` = `http://localhost:8000/api/v1`.

## Phase 2 parser

Import `MigraPilot-Phase2-Parser.postman_collection.json` too. It expects `token` and `project_id` from the Phase 1 register/create-project flow and saves `job_id` and `mapping_id` automatically. The upload body is multipart form-data with one file field named `file`; choose an XML fixture from `api/tests/fixtures/` or a ZIP containing XML files. Do not manually set `Content-Type`, because Postman must generate the multipart boundary.

## Phase 4A conversion

Import `MigraPilot-Phase4A-Conversion.postman_collection.json`. It expects an owner JWT in `token`, a parsed mapping in `mapping_id`, and a running API configured with server-side `GEMINI_API_KEY` (the default) or `ANTHROPIC_API_KEY` when `AI_PROVIDER=anthropic`. Never put an API key in Postman. **Convert mapping** saves `conversion_id`; **Regenerate conversion** creates a later version and updates that variable. A `503` means the provider is not configured, `429` can mean the application limit or provider quota was reached, and `502` means credentials, the provider call, or structured output failed. Generated SQL is returned for review and is never executed by these requests.

## Phase 5A shadow runs

The Phase 5A requests are appended to `MigraPilot-Phase4A-Conversion.postman_collection.json`; no additional workspace is needed. Set `conversion_id=2`, run **Phase 5A — Start shadow run**, then repeat **Poll shadow run report** until `status` is `completed` or `failed`. A correct sample conversion completes with `comparison_result: PASS`; a valid but different result completes with `FAIL`. **List shadow runs** is read-only. The negative request verifies a missing JWT returns `401`. These requests use only `orders_discount_v1` in the isolated shadow database and never require an AI provider call.

## Phase 6A AI Autopsy

Import `MigraPilot-Phase6A-Autopsy.postman_collection.json` and the updated local environment. First create a genuine FAIL with the explicit development CLI documented in the root README, then copy its printed `shadow_run_id` into the environment. **Start AI Autopsy** queues one Gemini request and saves `autopsy_id`; repeat **Poll AI Autopsy** manually until `completed` or `failed`, then run **List AI Autopsy history**. Do not use Collection Runner retries on the POST. Run 2 is intentionally used by **Reject PASS Shadow Run** and must return `422`. Set `other_token` only to a second local user's JWT for the ownership-isolation check. Provider keys belong only in Docker `.env`, never Postman.

Provider and Celery timeouts are terminal persisted failures; do not resubmit while a report remains queued or running. If a worker was hard-terminated, use the guarded stale-recovery CLI from the root README only after its configured stale threshold. The command verifies live Celery state before changing the record.
