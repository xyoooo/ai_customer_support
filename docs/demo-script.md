# Week 3 evidence-retrieval demo

## Demo claim

SupportPilot can securely ingest a support document into an isolated workspace and return
ranked, source-located evidence through the selected production C1+E1 pipeline. It does not
yet generate a conversational answer; that is the Week 4 milestone.

## Preparation

1. Use only synthetic or public documents.
2. From the repository root, provision the pinned offline model:

   ```powershell
   uv run python scripts/cache_rag_model.py
   ```

3. Start the application:

   ```powershell
   docker compose up --build
   ```

4. Open `http://localhost:5173/register`.

## Primary walkthrough

1. Register a new owner and workspace.
2. Create and upload a short Markdown support guide containing several policies, such as:
   returns are accepted for 30 days, damaged items require photographs, and refunds return
   to the original payment method.
3. Show the document first entering its processing state, then becoming `active` only after
   the worker completes parsing, chunking, embedding, and atomic persistence.
4. Ask: `How long are returns accepted?`
5. Show the returned source passage and its document, heading or page locator, and
   dense/lexical rank details.
6. Ask a paraphrase such as: `What proof should I provide for an item that arrived broken?`
   Show that semantic and lexical retrieval can find the relevant policy without exact
   wording.
7. Open the document page and show the immutable active version and completed durable job.

## Optional isolation walkthrough

1. Register a second account in a private browser window and create a different workspace.
2. Show that the second workspace cannot list, open, or retrieve evidence from the first
   workspace's document.
3. Explain that API authorization is backed by forced PostgreSQL row-level security rather
   than UI filtering alone.

## Evidence to mention

- C1 structure-aware chunks and pinned E1 384-dimensional embeddings were selected from a
  reviewed 70-case experiment rather than chosen by assumption.
- Indexing is idempotent and activates a version only after its full chunk set is ready.
- Search combines exact cosine retrieval, structural BM25, and deterministic reciprocal-rank
  fusion.
- Model files and uploaded documents are intentionally excluded from Git.
- The final GitHub workflow validates backend, frontend, security, contracts, containers,
  and the same real-model browser journey.

## Honest boundary

Do not present the displayed passages as a finished customer-support answer. Generated
answers, validated citations, clarification, abstention, conversation history, and account
recovery are planned for Week 4.
