"""Check the files needed by the portable Windows Ollama package."""

import argparse
from pathlib import Path
import sys
import zipfile


class PayloadError(ValueError):
    """The payload cannot be distributed as the requested build layout."""


def required_files(layout):
    files = ["ollama.exe", "libwinpthread-1.dll"]
    if layout == "native":
        files.extend([
            "lib/ollama/llama-server.exe",
            "lib/ollama/llama-quantize.exe",
        ])
        for version in (12, 13):
            prefix = f"lib/ollama/cuda_v{version}"
            files.extend([
                f"{prefix}/ggml-cuda.dll",
                f"{prefix}/cublas64_{version}.dll",
                f"{prefix}/cublasLt64_{version}.dll",
            ])
        # The upstream CUDA 13 backend links the CUDA runtime statically.
        files.append("lib/ollama/cuda_v12/cudart64_12.dll")
    elif layout != "legacy":
        raise PayloadError(f"Unknown build layout: {layout}")
    return files


def validate_payload(payload, layout):
    payload = Path(payload)
    for name in required_files(layout):
        target = payload / name
        if not target.is_file():
            raise PayloadError(f"Required payload file not found: {target}")
        if target.stat().st_size == 0:
            raise PayloadError(f"Required payload file is empty: {target}")


def validate_archive(archive, layout):
    archive = Path(archive)
    try:
        with zipfile.ZipFile(archive) as package:
            entries = {
                entry.filename.replace("\\", "/"): entry
                for entry in package.infolist()
                if not entry.is_dir()
            }
            for name in required_files(layout):
                entry = entries.get(name)
                if entry is None:
                    raise PayloadError(f"Required ZIP entry not found: {archive}: {name}")
                if entry.file_size == 0:
                    raise PayloadError(f"Required ZIP entry is empty: {archive}: {name}")
            # Read each member once to verify CRC as well as the directory listing.
            corrupt = package.testzip()
            if corrupt is not None:
                raise PayloadError(f"Corrupted ZIP entry: {archive}: {corrupt}")
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise PayloadError(f"Cannot validate ZIP {archive}: {error}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--payload", type=Path, help="Staged payload directory")
    source.add_argument("--archive", type=Path, help="Final ZIP package")
    parser.add_argument("--layout", required=True, choices=("native", "legacy"))
    arguments = parser.parse_args()
    try:
        if arguments.payload is not None:
            validate_payload(arguments.payload, arguments.layout)
        else:
            validate_archive(arguments.archive, arguments.layout)
    except (PayloadError, OSError) as error:
        print(f"Payload verification failed: {error}", file=sys.stderr)
        return 1
    print(f"Verified {arguments.layout} payload: {arguments.payload or arguments.archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
