# Week 1 demo script

1. Run `docker compose up --build` from a clean checkout.
2. Open `http://localhost:5173/register` and create Workspace A.
3. Open a private browser window, register a second account and Workspace B.
4. Use the API documentation at `http://localhost:8000/docs` to add the second account to Workspace A as a viewer.
5. Sign in as the viewer and show that members can be read but membership changes return `403`.
6. Attempt to request Workspace B with Workspace A's owner token and show the non-enumerating `404` response.
7. Run `uv run pytest --cov=apps --cov=packages` and show the direct runtime-role RLS tests and coverage gate.
8. Show the migration/runtime credentials, RLS migration, ADRs, and threat-model limitations.

