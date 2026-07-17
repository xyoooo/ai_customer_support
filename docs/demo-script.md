# Week 2 demo script

1. Run `docker compose up --build` from a clean checkout.
2. Open `http://localhost:5173/register` and create Workspace A.
3. Open a private browser window, register a second account and Workspace B.
4. Use the API documentation at `http://localhost:8000/docs` to add the second account to Workspace A as a viewer.
5. Sign in as the viewer and show that members can be read but membership changes return `403`.
6. Attempt to request Workspace B with Workspace A's owner token and show the non-enumerating `404` response.
7. As the owner, upload a small synthetic Markdown document and show its queued state.
8. Wait for the worker to activate the immutable version, then open the document page and show version metadata and the completed durable job.
9. Explain the upload controls: streaming byte limit, filename sanitization, type/signature agreement, SHA-256 duplicate detection, application-generated object keys, and the development-only no-op scanner.
10. Show migration `20260716_0002`, forced RLS on `documents`, `document_versions`, and `jobs`, and the expired-lease/stale-worker tests.
11. Run `uv run pytest --cov=apps --cov=packages` and show the 85% coverage gate, direct cross-workspace denial, durable retry/dead-letter behavior, and migration preservation test.
12. Show ADR 0004 and the Week 2 threat-model limitations, especially synthetic/public data only and the future dedicated worker credential and malware scanner.
