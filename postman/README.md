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
