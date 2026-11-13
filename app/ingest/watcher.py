import threading
import time
from pathlib import Path

from app.ingest.pipeline import ingest_file


def watch(engine, folder, interval: float = 5.0, stop: threading.Event = None) -> None:
    """Poll `folder` and ingest new PDFs. Idempotent: duplicates are skipped by content hash."""
    stop = stop or threading.Event()
    seen = {}
    while not stop.is_set():
        for p in Path(folder).glob("*.pdf"):
            key = (p.stat().st_size, p.stat().st_mtime)
            if seen.get(p) != key:
                time.sleep(0.2)  # let a copy in progress finish
                if p.stat().st_size == key[0]:
                    ingest_file(engine, p)
                    seen[p] = key
        stop.wait(interval)
