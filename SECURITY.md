# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities. Report
them privately by emailing the maintainers (or opening a private security
advisory on GitHub if available).

When reporting, include:

- the affected version(s) / commit,
- a description of the vulnerability and its impact,
- a minimal reproduction (config snippet + commands) where possible.

You should receive a response within a reasonable timeframe; please do not
disclose the issue publicly until it has been addressed.

## Security design notes

- **Secrets** — API keys are never hard-coded. Use `api_key_env` /
  `${ENV_VAR}` in `minions.yaml` and export keys in your shell; the bridge
  subprocess inherits the parent environment. Never commit `.env` files
  (see `.gitignore`).
- **Data locality** — by design, the long context is processed by the local
  worker and only compact sub-task summaries are sent to the cloud.
- **Supply chain** — dependencies are pinned loosely (`>=`) in
  `pyproject.toml`; review dependency upgrades in CI.

## Supported versions

Security fixes are applied to the latest release and, where feasible, to the
most recent minor version.
