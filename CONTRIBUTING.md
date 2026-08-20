# Contributing to minions-dsh

Thanks for your interest in contributing! `minions-dsh` is MIT-licensed open
source, and we welcome bug reports, feature requests, documentation, and code.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to contribute](#ways-to-contribute)
- [Development setup](#development-setup)
- [Project conventions](#project-conventions)
- [Pull request workflow](#pull-request-workflow)
- [Testing](#testing)
- [Documentation](#documentation)
- [License](#license)

## Code of Conduct

This project adheres to the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating you agree to uphold it.

## Ways to contribute

- **Report bugs** — open an issue with a minimal reproducer (config + command).
- **Suggest features** — especially new local platforms or protocol variants.
- **Improve docs** — the docs live in `docs/`; fix typos, add examples.
- **Write code** — see the open issues and the sections below.

## Development setup

Requirements: **Python 3.10+**, **Node.js 18+** (for the plugin).

```bash
git clone https://github.com/kaijiayang/minions-dsh.git
cd minions-dsh

# Python
pip install -e ".[dev]"

# TypeScript plugin
cd dsh-plugin && npm install && npm run build && cd ..
```

## Project conventions

- **Python** — target Python 3.10+; keep the core `minions/` library free of
  hard dependencies on optional provider SDKs (import them lazily inside
  functions, as `minions/clients/__init__.py` already does).
- **Bridge contract** — `dsh-plugin/python/minions_bridge.py` must keep the
  strict contract: **one JSON object in on stdin, one JSON object out on
  stdout, everything else to stderr.** Never print logs to stdout.
- **Config** — any new config option must be added to `minions/config.py`,
  `config.schema.json`, and documented in `docs/CONFIGURATION.md`.
- **Secrets** — never commit API keys. Use `api_key_env` / `${VAR}`.

## Pull request workflow

1. Fork the repository and create a branch: `git checkout -b feat/your-change`.
2. Make your change with tests.
3. Run the checks below.
4. Open a pull request against `main` describing the change and the testing done.

## Testing

```bash
# Python unit tests
python -m pytest tests/

# Bridge offline self-test
python dsh-plugin/python/minions_bridge.py --self-test

# Validate a config example
python dsh-plugin/python/minions_bridge.py --validate-config examples/configs/minions.lmstudio.yaml

# TypeScript build + smoke test
cd dsh-plugin
npm run build
npm run smoke
```

A PR that adds a new client or a config option **must** include tests:

- client tests go in `tests/test_openai_compat.py` (mock the HTTP layer);
- config tests go in `tests/test_config.py`.

## Documentation

User-facing docs live in `docs/` and are linked from `README.md`. When you
change behavior, update the relevant doc in the same PR. The README is
maintained in English (`README.md`) and Chinese (`README.zh-CN.md`) — keep
them in sync.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
