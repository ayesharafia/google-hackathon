# Hosted provider sign-in needed for remote MCP

Status: proposal for review. The remote MCP work uncovered a missing prerequisite: hosted workbench login accepts passwords, while a provisioned OAuth/OIDC identity has no password login. The synthetic browser fixture links both identity types by direct database modification; that is test-only and is not a usable or safe production onboarding flow.

## Proposed experience

When hosted provider sign-in is configured, show **Sign in with your organization** alongside the existing password form. The user signs in at the configured identity provider and returns to the workbench already signed in. Only an existing active PhysiCore account with exactly matching verified issuer and subject can sign in. Administrators must provision that account and project membership through the existing trusted provisioning process. No account is linked by matching an email address or by entering a subject in the browser.

## Authentication design

Use one explicitly configured HTTPS OpenID Connect provider and registered public workbench client. Validate discovery metadata and endpoints against the configured issuer and approved origins; do not accept provider or redirect URLs from the browser. Use authorization code flow with PKCE S256, transaction-specific random state and nonce. Bind state to the initiating browser with a short-lived secure, HttpOnly, SameSite cookie and durable, one-use server-side transaction record. Enforce an exact preconfigured callback URL and consume the transaction atomically. Reject missing, expired, reused or mismatched state, code, cookie, issuer or nonce. Exchange codes only at the configured HTTPS token endpoint with bounded timeouts and no redirect or token logging.

Verify the returned ID token's signature, issuer, workbench client audience, expiration, issued-at and nonce; use only its verified issuer and subject to look up the existing active user. Issue a separate opaque, random, server-side hosted browser session; persist only its hash and expiry and deliver it in a secure HttpOnly SameSite cookie. The remote MCP token is a separate access token, has a distinct resource audience and cannot authenticate normal application routes. Do not expose the provider ID token, access token, authorization code or refresh token to browser JavaScript or logs; discard provider tokens after validation. No automatic account creation, account linking or refresh tokens in this slice.

Extend the hosted application gateway to recognize the browser cookie for normal workbench operations, rechecking session and membership as today. State-changing cookie-authenticated requests must pass the existing same-origin checks. Preserve existing bearer/password sessions and explicitly reject cookies at remote MCP. On sign-out revoke the browser session and clear the cookie; expired or revoked sessions lose access. Ensure the client does not send an empty bearer header in cookie mode. Browser project switching and sign-out clear AI keys and private views as before.

The server requires explicit issuer, discovery endpoint, client ID and public callback origin. It does not deploy, register a client or select a provider for the user. A provider supporting exact redirect registration and OIDC/PKCE is needed. OAuth client registration and MCP access tokens remain separate; the provider must issue signed access tokens with verified client identity and the MCP-only audience expected by the remote connector.

## Verification

Use a disposable synthetic OIDC provider and real browser: sign-in, provisioned account and project access, remote consent, exact review and logout. Reject account linking by email, unprovisioned/inactive subjects, wrong nonce/state/cookie/issuer/audience, reused/expired codes, hostile redirects, cross-origin changes and remote tokens on ordinary routes. Test token secrecy, session expiry/revocation, simultaneous browsers and unaffected password access. Recheck desktop/phone/enlarged controls against the full interface law. No real provider, live customer account, deployment or scientific validation is inferred.

References: [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html), [OAuth Security Best Current Practice](https://datatracker.ietf.org/doc/html/rfc9700).
