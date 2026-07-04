from __future__ import annotations

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Access JWT — Authorization: Bearer <access_token>
http_bearer = HTTPBearer(
    scheme_name="BearerAuth",
    description="JWT access token. Example: Authorization: Bearer eyJhbGciOiJIUzI1NiIs...",
    auto_error=False,
)

# Refresh token — Authorization: Bearer <refresh_token> on /auth/refresh and /auth/logout
http_bearer_refresh = HTTPBearer(
    scheme_name="BearerRefresh",
    description="Refresh token for token rotation and logout.",
    auto_error=False,
)

BearerCredentials = HTTPAuthorizationCredentials
