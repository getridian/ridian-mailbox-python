# Contributing

Use Python 3.10 or newer on Linux or macOS. Tests use synthetic responses and
temporary state files; they do not create real mailboxes or need API keys.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
python -m build
python -m twine check dist/*
python scripts/check_dist.py
```

Keep changes focused. Include regression tests for changed behavior and update
the README or API reference when the public contract changes. Never include
mailbox state, access tokens, claim secrets or personal email in issues, fixtures,
logs or commits. Use synthetic values and reserved example domains.

Report vulnerabilities through [private reporting](SECURITY.md).

## Releases

1. Update the version in `pyproject.toml` and `src/ridian_mailbox/__init__.py`.
2. Update the changelog and review the package metadata and archive contents.
3. Merge after CI passes. Create a GitHub prerelease tagged `v<version>` for an alpha.
4. The release workflow verifies that the tag matches the version, runs tests,
   builds and checks archives, then uploads those exact artifacts to the `pypi` job.
5. An environment reviewer approves publication. Only that job receives an OIDC
   token; PyPI Trusted Publishing is scoped to this repository, `release.yml` and
   the `pypi` environment. No long-lived PyPI token is used.
6. Verify installation and file hashes from PyPI. Update the README's install pin
   and the website's generated guides after the release is available.

GitHub Actions are pinned to commit hashes. Dependabot proposes updates; review
upstream changes before merging. Keep package versions immutable once published.
