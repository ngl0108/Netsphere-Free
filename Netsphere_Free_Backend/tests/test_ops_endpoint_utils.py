import subprocess

from app.api.v1.endpoints import ops


def test_docker_compose_related_status_includes_netsphere_and_legacy_names(monkeypatch):
    monkeypatch.setattr(ops, "_read_text", lambda _path: "docker-sock")

    def fake_run_docker(_args, timeout_seconds=10):
        return subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=(
                "netsphere-backend\tUp 5 minutes\n"
                "netmanager-celery-worker\tUp 3 minutes\n"
                "postgres\tUp 9 minutes\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(ops, "_run_docker", fake_run_docker)

    rows = ops._docker_compose_related_status()

    assert rows == [
        {"name": "netsphere-backend", "status": "Up 5 minutes"},
        {"name": "netmanager-celery-worker", "status": "Up 3 minutes"},
    ]
