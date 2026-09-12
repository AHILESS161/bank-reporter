import threading
from types import SimpleNamespace

from app.local_runtime import dispatch_task


def test_local_task_backend_runs_without_redis(monkeypatch):
    completed = threading.Event()

    class Task:
        @staticmethod
        def run(value):
            if value == "ok":
                completed.set()

    monkeypatch.setattr(
        "app.local_runtime.get_settings", lambda: SimpleNamespace(task_backend="local")
    )
    handle = dispatch_task(Task(), "ok")
    assert handle.id
    assert completed.wait(2)
