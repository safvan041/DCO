# src/dco/watcher.py
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ReloadHandler(FileSystemEventHandler):
    def __init__(self, on_change, patterns=None):
        self.on_change = on_change
        self.patterns = patterns or [".env", ".yaml", ".yml", ".json"]

    def on_modified(self, event):
        # watchdog sometimes sends directory events; ensure it's a file
        try:
            path = event.src_path
            if any(path.endswith(p) for p in self.patterns):
                self.on_change(path)
        except Exception:
            pass


def start_watcher(path: str, on_change):
    observer = Observer()
    handler = ReloadHandler(on_change)
    observer.schedule(handler, path, recursive=False)
    thread = threading.Thread(target=observer.start, daemon=True)
    thread.start()
    return observer
