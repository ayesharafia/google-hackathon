# Hosted provider sign-in implementation plan

> Execute inline under the repository's one-implementer rule.

**Goal:** Allow an already-provisioned OIDC user to securely sign into the hosted workbench and approve remote MCP actions.

**Architecture:** An opt-in authorization-code/PKCE client uses pinned provider metadata, single-use browser-bound state and nonce, and verifies the ID token. It issues a distinct opaque hosted browser cookie, accepted only on the normal application gateway with same-origin enforcement. Remote MCP tokens remain excluded from app routes.

**Tech stack:** FastAPI, PyJWT, urllib, SQLite/PostgreSQL metadata, native workbench JS, synthetic provider and browser tests.

**Spec:** `docs/superpowers/specs/2026-10-27-hosted-provider-signin-proposal.md`, approved 27 October 2026.

## Constraints

Disabled unless configured, HTTPS provider and callback; no account auto-provision/link by email, provider-token storage, refresh tokens, live provider calls, deployment or physics changes. Opaque session cookies HttpOnly, Secure, SameSite; exact callback/state/nonce/PKCE and issuer/audience validation. Existing password and local access preserved. All provider responses and authorization codes are untrusted; secrets never logged.

## Steps completed locally

1. Implement transaction store with bounded, expiring and atomically consumed browser-bound states, and synthetic tests for replay, mismatch and concurrency.
2. Add strict configured HTTPS provider discovery, authorization and token exchange with no redirects, bounded responses and verified ID-token issuer, audience and nonce. Exercise synthetic provider success and refusal cases.
3. Add hosted cookie session issuance, gateway authentication, cross-origin enforcement and logout while retaining password and remote-token isolation. Test unknown/inactive users and session revocation.
4. Wire workbench sign-in/status, test real browser using a disposable synthetic provider, then verify project consent and reviewed action. Inspect desktop, phone, enlargement, interaction and full design law.
5. Resume REMOTE-MCP-001, run focused and broad regressions, note unverified real provider/PostgreSQL/deployment, document and commit locally.
