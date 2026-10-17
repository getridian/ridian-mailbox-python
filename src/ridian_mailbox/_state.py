"""Private, durable storage shared by the library and CLI."""

import json
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Any


def load_or_create_state(path: Path, base_url: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd) as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise ValueError("State must be a private regular file (chmod 600).")
            state = json.load(handle)
        if not isinstance(state, dict) or state.get("base_url") != base_url:
            raise ValueError("State belongs to another API origin. Use a separate state file.")
        if not isinstance(state.get("setup_token"), str) or not re.fullmatch(
            r"ridian_setup_[a-f0-9]{64}", state["setup_token"]
        ):
            raise ValueError("State has no valid setup credential. Restore a private backup.")
        return state
    state = {"base_url": base_url, "setup_token": "ridian_setup_" + secrets.token_hex(32)}
    with os.fdopen(fd, "w") as handle:
        json.dump(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(state, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare_curl(path: Path, state: dict[str, Any]) -> None:
    """Prepare private curl files locally, reusing the durable setup identity."""
    token = state["setup_token"]
    if not re.fullmatch(r"ridian_setup_[a-f0-9]{64}", token):
        raise ValueError("Invalid saved setup credential.")
    header = Path(str(path) + ".headers")
    response = Path(str(path) + ".response.json")
    # Do not overwrite an existing response: it may be the only saved proof.
    for target, content in [(header, "Authorization: Bearer " + token + "\n"), (response, "")]:
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = os.open(target, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(fd) as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                    raise ValueError("curl files must be private regular files.")
                if target == header and handle.read() != content:
                    raise ValueError("Header belongs to a different setup credential.")
        else:
            with os.fdopen(fd, "w") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
