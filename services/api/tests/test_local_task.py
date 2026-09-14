from app.local_task import LocalTask, LocalTaskRegistry


def test_local_task_registry_runs_plain_and_bound_tasks():
    registry = LocalTaskRegistry()

    @registry.task(name="plain")
    def plain(value):
        return value + 1

    @registry.task(name="bound", bind=True, autoretry_for=(ConnectionError,))
    def bound(task, value):
        return task.__name__, value * 2

    assert isinstance(plain, LocalTask)
    assert plain.run(4) == 5
    assert bound.run(6) == ("bound", 12)
