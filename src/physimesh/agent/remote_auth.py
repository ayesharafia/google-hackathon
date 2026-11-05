"""Verification for explicitly configured OAuth JWT access tokens."""

from urllib.parse import urlsplit

import jwt

from physimesh.platform.identity import Denied


def https_url(value):
    url = urlsplit(value)
    return (
        url.scheme == "https"
        and bool(url.hostname)
        and not url.username
        and not url.password
        and not url.fragment
    )


class AccessVerifier:
    def __init__(self, issuer, audience, jwks_url):
        if not all(https_url(x) for x in (issuer, audience, jwks_url)):
            raise ValueError("Remote OAuth issuer, resource audience and JWKS require HTTPS URLs.")
        self.issuer, self.audience = issuer, audience
        self.keys = jwt.PyJWKClient(jwks_url, timeout=5, cache_keys=False, lifespan=300)

    def verify(self, token):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 16384:
                raise ValueError()
            header = jwt.get_unverified_header(token)
            if header.get("typ") not in ("at+jwt", "application/at+jwt") or header.get("alg") not in (
                "RS256",
                "ES256",
            ):
                raise ValueError()
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "client_id"]},
            )
            if claims["aud"] not in (self.audience, [self.audience]):
                raise ValueError("Remote tokens must be scoped to this resource alone.")
            for name in ("sub", "client_id"):
                value = claims[name]
                if (
                    not isinstance(value, str)
                    or not value
                    or len(value) > 512
                    or any(ord(c) <= 32 or ord(c) == 127 for c in value)
                ):
                    raise ValueError()
            return claims
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, OSError):
            raise Denied("Invalid remote OAuth access token.") from None
