#!/usr/bin/env python3
r"""
Genereert een .sha256-bestand voor een release-exe.

Gebruik dit bij het publiceren van een nieuwe GitHub release, en upload
het resulterende .sha256-bestand als extra asset naast de .exe.
De auto-updater in de app controleert deze hash voordat een update
wordt geinstalleerd (zie UpdateWorker.run in yt_mp3_converter.py).

Gebruik:
    python make_checksum.py dist\YT-MP3-Converter-Setup-1.0.2.exe
"""
import hashlib
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("Gebruik: python make_checksum.py <pad-naar-exe>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Bestand niet gevonden: {target}")
        sys.exit(1)

    sha256 = hashlib.sha256()
    with open(target, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    digest = sha256.hexdigest()
    out_path = target.with_suffix(target.suffix + ".sha256")
    out_path.write_text(digest + "\n", encoding="utf-8")

    print(f"SHA256: {digest}")
    print(f"Geschreven naar: {out_path}")
    print("Upload dit bestand als extra asset bij je GitHub release.")


if __name__ == "__main__":
    main()
