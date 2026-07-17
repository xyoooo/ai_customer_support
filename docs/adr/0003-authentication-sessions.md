# ADR 0003: Use short-lived JWT access tokens with rotating opaque sessions

- Status: accepted
- Date: 2026-07-13
- Last reviewed: 2026-07-17

## Context

The browser application needs efficient authorization on normal API requests, explicit logout, refresh revocation, replay detection, and a future path to OAuth or enterprise identity-provider linking. Browser-accessible long-lived credentials would create unnecessary exposure if script execution is compromised.

## Decision drivers

- Keep access credentials short-lived.
- Support logout and server-side refresh revocation.
- Detect reuse of a rotated refresh token.
- Avoid a database lookup on every normal API request at the current stage.
- Keep future external identity-provider linking possible.

## Options comparison

| Option | Advantages | Limitations |
|---|---|---|
| Short-lived JWT access token plus rotating opaque refresh session | Normal API checks are local; refresh and logout remain controllable; rotation supports replay detection; works with browser and API clients | More lifecycle logic; access tokens remain valid until their short expiry; secure cookie and CSRF design are required |
| Opaque server-side session cookie | Simple revocation and logout; minimal credential data in the browser; mature web pattern | Requires a session lookup or cache on requests; browser-cookie APIs need CSRF protection; less convenient for non-browser clients |
| Long-lived JWT with no server-side session | Minimal storage and request-time infrastructure | Immediate logout and revocation are difficult; stolen tokens remain useful longer; poor replay control |
| External OAuth/OIDC provider from the start | Delegates login security, MFA, recovery, and federation; useful for enterprise SSO | Adds provider configuration, redirect flows, external dependency, and possible cost before the product needs federation; application authorization is still required |

## Decision

Use 15-minute signed access JWTs and random opaque refresh tokens.

- Store only SHA-256 hashes of refresh secrets.
- Put refresh tokens in HTTP-only, SameSite cookies and use HTTPS-only cookies in production.
- Rotate the refresh token on every successful use and link replacement sessions.
- Revoke the entire token family when replay is detected.
- Keep browser access tokens only in memory.
- Hash passwords with Argon2 through `pwdlib`.

## Why this suits the current stage

The API and web application are first-party components, traffic is modest, and federation is not yet a product requirement. The hybrid design keeps normal authorization fast while retaining control over long-lived sessions, logout, and suspicious replay.

It also demonstrates the distinction between authentication, session management, and workspace authorization without making an external identity vendor a prerequisite for local development.

## Consequences

### Advantages accepted

- Normal API requests do not require session-table reads.
- Refresh, logout, and session-family revocation are server controlled.
- Password and refresh secrets are not stored in recoverable form.
- OAuth/OIDC identities can later link to the same internal user model.

### Limitations accepted

- A revoked user's access token can remain valid for up to its short expiry unless an additional denylist or token-version check is introduced.
- Rotation races, replay detection, cookie settings, CORS, and CSRF behavior require dedicated tests.
- Production requires HTTPS and a strong signing secret managed outside the repository.
- Building password authentication creates recovery and abuse-prevention responsibilities.

## When to reconsider

- Prefer a managed OAuth/OIDC provider when social login, MFA, password recovery, enterprise SSO, SCIM, or compliance requirements become part of the product.
- Prefer opaque server-side sessions if immediate per-request revocation becomes more important than avoiding session lookups.
- Add access-token denylisting or user token-version checks when high-risk account suspension must take effect before the 15-minute expiry.
- Revisit cookie and token placement if the frontend and API move to materially different trust or domain boundaries.
