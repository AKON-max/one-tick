# Security Policy

## Reporting

This repository is maintained by a single developer. Do not open a public issue containing a working credential, private key, dump, or personal data. Contact the repository owner privately instead.

## Secrets

The repository intentionally tracks only `.env.example`. Local `.env` files are ignored.

If a credential was ever committed or pasted into an issue:

1. Rotate it immediately at the provider.
2. Remove it from the current branch.
3. Check Git history and CI logs.
4. Document the incident without publishing the secret.

## Current security limitations

- The browser session cookie is currently readable by frontend code for route guarding.
- REST endpoints do not have a single global rate limiter.
- WebSocket state and model-provider state are process-local.
- Production deployments must add HTTPS, secure cookie flags, monitoring, and backups.