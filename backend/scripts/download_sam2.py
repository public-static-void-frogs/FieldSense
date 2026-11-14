"""One-time model preparation; runtime never downloads weights."""

import hashlib
import os
from pathlib import Path
from urllib.request import urlretrieve

URL = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt"
SHA256 = "65b50056e05bcb13694174f51bb6da89c894b57b75ccdf0ba6352c597c5d1125"
TARGET = Path(__file__).resolve().parents[1] / ".cache/models/sam2_hiera_tiny.pt"

if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temporary = TARGET.with_suffix(".download")
    try:
        urlretrieve(URL, temporary)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if digest != SHA256:
            raise RuntimeError("Downloaded SAM2 checkpoint failed SHA256 verification")
        print(f"Downloaded official SAM2 tiny checkpoint, sha256={digest}")
        os.replace(temporary, TARGET)
    finally:
        temporary.unlink(missing_ok=True)
