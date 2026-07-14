# ADR 0003: Short-lived JWT access tokens with rotating opaque sessions

- Status: accepted
- Date: 2026-07-13

## Context

The API needs stateless authorization on normal requests, explicit logout, refresh revocation, and a future path to OAuth account linking.

## Decision

Use 15-minute signed access JWTs and random refresh tokens. Store only SHA-256 hashes of refresh secrets. Put refresh tokens in HTTP-only SameSite cookies, rotate them on every use, link replacements, and revoke the entire token family when replay is detected. Hash passwords with Argon2 through `pwdlib`.

## Consequences

Normal requests avoid session lookups while refresh and logout remain controllable. The web app keeps access tokens only in memory. Production requires HTTPS cookies and a deployment secret of at least 32 characters.

