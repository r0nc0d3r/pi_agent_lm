#!/usr/bin/env python3
"""Download Gemma 4 E2B `.litertlm` from Hugging Face (~2.5 GB).

Public model — anonymous download; no HF token or account required.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

HF_REPO = "litert-community/gemma-4-E2B-it-litert-lm"
DEFAULT_FILENAME = "gemma-4-E2B-it.litertlm"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for the model file (default: current directory)",
    )
    p.add_argument(
        "--filename",
        default=DEFAULT_FILENAME,
        help=f"File name in the repo (default: {DEFAULT_FILENAME})",
    )
    args = p.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        repo_id=HF_REPO,
        filename=args.filename,
        local_dir=str(out),
    )
    print(path)


if __name__ == "__main__":
    main()
