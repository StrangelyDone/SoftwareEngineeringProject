---
title: "YouTube OAuth 2.0 Flow and Token Expiration"
author: "Pranay Sanjan Kanneti"
created: 2026-11-26
tags: [youtube-mcp, resource, oauth]
type: resource
---

# YouTube OAuth 2.0 Flow and Token Expiration

## Summary
The YouTube Data API uses OAuth 2.0 when an application accesses private user data or performs actions on a user's behalf. An authorization-code flow lets the user grant scoped access without sharing their password with the application. During development, external OAuth apps left in Testing issue refresh tokens that expire after seven days, so reauthorization must be an expected recovery path.

## Key Technical Details
- **Authorization flow:** Send the user to Google's authorization server with the required scopes; exchange the returned authorization code for tokens, then send the access token as a Bearer token on authorized YouTube API requests.
- **Offline access:** A web-server app requests `access_type=offline` when it needs a refresh token to obtain new access tokens without prompting the user each time.
- **Testing-mode expiry:** For an external-user OAuth consent screen with publishing status `Testing`, refresh tokens expire after **7 days**, except when the requested scopes are limited to basic name, email, and profile scopes. YouTube data scopes are outside that exception.
- **Recovery and security:** Handle refresh failures by requiring the user to authorize again; request only needed scopes and store credentials securely. Never put tokens or client secrets in notes, logs, fixtures, or source control.

## Project Traceability & Connections
- **Related Requirements:** FR-3, FR-4, FR-5, TQ-4
- **Related Notes:** [[index]], [[youtube-api-quota-system]], [[provider-pattern-isolation]]
- **Source:** Google OAuth 2.0 overview, “Refresh token expiration” (https://developers.google.com/identity/protocols/oauth2#expiration); YouTube Data API authentication (https://developers.google.com/youtube/data/guides/authentication)
