# Changelog

## 0.1.0a4 — unreleased

- Public SDK repository, Python API reference, and source and issue links in package metadata.
- CLI uses the same request validation and error handling as the Python library.
- Validate setup credentials before saving and preserve the original setup identity.
- Reject non-finite timeouts, boolean page limits and repeated pagination cursors.
- Type annotations for public methods and a `py.typed` marker for editors.

## 0.1.0a3 — 2026-10-17

- Initial PyPI alpha: private receiving mailbox setup and recovery, message and
  attachment reads, explicit event acknowledgement, webhook configuration and CLI.
- Explicit SDK request identification and MIT licensing.
