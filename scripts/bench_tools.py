"""Install pinned Linux x86-64 tools for the availability benchmark."""

from __future__ import annotations

import hashlib
import platform
import shutil
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

TOOL_DIR = Path(".bench-tools")
RELEASES = {
    "sloth": (
        "https://github.com/slok/sloth/releases/download/v0.11.0/sloth-linux-amd64",
        "a28a1e3f35830b362eba5ac5b98635e9ab426cf4448b0dc623ba2aa8c5ad5a52",
    ),
    "pyrra": (
        "https://github.com/prometheus-community/pyrra/releases/download/"
        "v0.8.4/pyrra_0.8.4_Linux_x86_64.tar.gz",
        "8f54ace185ea2aaaeb4f470e07ec16d43e79a4b755b2616472071c134e93517b",
    ),
    "oslo": (
        "https://github.com/OpenSLO/oslo/releases/download/v0.13.0/oslo-0.13.0-linux-amd64",
        "9d428655f0a7bee0324aa38c3ce64e68316ee2b2277d61e6f5245c5a8fa2cecb",
    ),
}


def verify(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("SHA-256 checksum mismatch")


def install(name: str, url: str, checksum: str) -> None:
    with TemporaryDirectory(dir=TOOL_DIR) as temp:
        download = Path(temp) / "download"
        with urlopen(url, timeout=60) as source, download.open("wb") as dest:
            shutil.copyfileobj(source, dest)
        verify(download, checksum)
        binary = download
        if url.endswith(".tar.gz"):
            binary = Path(temp) / name
            with tarfile.open(download) as archive:
                member = archive.getmember(name)
                if not member.isfile():
                    raise ValueError(f"{name} archive member is not a regular file")
                source = archive.extractfile(member)
                assert source is not None
                with source, binary.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
        binary.chmod(0o755)
        binary.replace(TOOL_DIR / name)


def main() -> None:
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise SystemExit("Pinned binaries require Linux x86-64. See benchmarks/README.md.")
    TOOL_DIR.mkdir(exist_ok=True)
    for name, (url, checksum) in RELEASES.items():
        try:
            install(name, url, checksum)
        except (OSError, ValueError, tarfile.TarError, KeyError) as exc:
            raise SystemExit(f"Could not install {name}: {exc}") from exc
        print(f"Installed {TOOL_DIR / name}")


if __name__ == "__main__":
    main()
