# Remote MCP implementation plan

> Execute inline under the repository's one-implementer policy.

**Goal:** Connect authorized remote MCP clients to existing project actions, preserving reviewed mutations.

**Architecture:** An opt-in hosted HTTP transport validates external OAuth access tokens and maps them to a provisioned user and explicit one-project client consent. Each HTTP request obtains its own scoped context; the MCP SDK dispatches the existing registry and project services, with no process-global credential. Existing stdio remains intact.

**Tech stack:** FastAPI/Starlette, official Python MCP SDK, JWT verification, SQLite/PostgreSQL metadata and native browser controls.

**Spec:** `docs/superpowers/specs/2026-10-27-remote-mcp-proposal.md`, approved by owner on 27 October 2026.

## Constraints

Disabled by default; hosted authenticated mode; explicit HTTPS endpoint and OAuth settings; no real provider, paid call, deployment, publication or physics change. Per-request issuer/audience/token type/client validation, user and membership recheck, bounded consent and trusted human review. Test actual HTTP MCP SDK with synthetic tokens, parallel users, revocation and previous stdio behavior. Interface law and real browser checks apply to consent controls.

## Delivery sequence completed locally

1. Add a versioned remote consent migration and tests for authorized issuance, role attenuation, expiry, client binding and revocation. Reuse existing transactional lock and project authority.
2. Add opt-in OAuth settings and JWT access-token verification; validate request metadata and explicit HTTPS issuer/audience/JWKS, return protected-resource discovery without exposing private data. Verify invalid token classes and HTTP security boundaries.
3. Adapt the MCP server to resolve a request-specific scoped bridge and add stateless Streamable HTTP lifecycle. Test real SDK tools and resources, concurrent users and exact approval/receipt flow; rerun stdio tests.
4. Add workbench consent and revocation controls, test interactions with a disposable synthetic hosted fixture, inspect desktop/phone/enlarged states and review every applicable owner design rule.
5. Run targeted and existing regressions, document configuration and limitations, preserve evidence and commit locally.
