"""Reject unexpected files and missing metadata in release archives."""

import email
import tarfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
wheels = list(dist.glob("*.whl"))
sdists = list(dist.glob("*.tar.gz"))
assert len(wheels) == len(sdists) == 1, "Build exactly one wheel and one sdist"
runtime = {
    "ridian_mailbox/__init__.py",
    "ridian_mailbox/client.py",
    "ridian_mailbox/cli.py",
    "ridian_mailbox/_state.py",
    "ridian_mailbox/py.typed",
}
with zipfile.ZipFile(wheels[0]) as archive:
    names = set(archive.namelist())
    metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
    assert len(metadata_paths) == 1
    prefix = metadata_paths[0].rsplit("/", 1)[0]
    allowed = runtime | {
        f"{prefix}/{name}"
        for name in (
            "METADATA",
            "WHEEL",
            "RECORD",
            "entry_points.txt",
            "top_level.txt",
            "licenses/LICENSE",
        )
    }
    assert names == allowed, f"Unexpected wheel files: {names ^ allowed}"
    metadata = email.message_from_bytes(archive.read(metadata_paths[0]))
    assert metadata["Name"] == "ridian-mailbox"
    assert metadata["License-Expression"] == "MIT"
    assert not metadata.get_all("Requires-Dist"), "Runtime must remain dependency-free"
    assert archive.read(f"{prefix}/licenses/LICENSE") == (root / "LICENSE").read_bytes()
    for name in runtime:
        assert archive.read(name) == (root / "src" / name).read_bytes()

with tarfile.open(sdists[0]) as archive:
    for member in archive.getmembers():
        assert not member.issym() and not member.islnk(), "No links in source archive"
        relative = Path(*Path(member.name).parts[1:])
        assert ".." not in relative.parts
        if member.isdir():
            continue
        allowed = (
            str(relative) in {"LICENSE", "README.md", "pyproject.toml", "PKG-INFO", "setup.cfg"}
            or str(relative) in {"src/" + name for name in runtime}
            or str(relative)
            in {"tests/" + path.name for path in (root / "tests").glob("test_*.py")}
            or (
                relative.parent == Path("src/ridian_mailbox.egg-info")
                and relative.name
                in {
                    "PKG-INFO",
                    "SOURCES.txt",
                    "dependency_links.txt",
                    "entry_points.txt",
                    "top_level.txt",
                }
            )
        )
        assert allowed, f"Unexpected sdist file: {relative}"

print("Wheel and sdist file allowlists, source bytes, MIT license and metadata verified.")
