# MigraPilot Postman API checks — Phase 1

1. Start the services at the project root: `docker compose up --build`.
2. Open Postman → Import: `MigraPilot-Phase1.postman_collection.json` and `MigraPilot-Local.postman_environment.json`.
3. Choose the **MigraPilot Local** environment.
4. Run the collection **in its presented order**. Registration generates a new disposable local test account and saves a JWT (`token`); project creation saves `project_id`.
5. Confirm every test passes. No external API key is required for Phase 1.

Note: `local_test_password` is a disposable DEMO account password. Never store real user credentials or production tokens in exported environments. The collection modifies (then deletes) a demo project in your local database, and the registration test creates a user. Keep it on local development only.

API base: `{{base_url}}` = `http://localhost:8000/api/v1`.
