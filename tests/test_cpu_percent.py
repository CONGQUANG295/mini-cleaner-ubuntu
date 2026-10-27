"""CPU% process phải tính trên tổng logical cores, không phải per-core như top."""

from core.system_monitor import normalize_cpu_percent


def test_normalize_divides_by_logical_cpu_count(monkeypatch):
    monkeypatch.setattr(
        "core.system_monitor.psutil.cpu_count",
        lambda logical=True: 8,
    )
    assert normalize_cpu_percent(80.0) == 10.0
    assert normalize_cpu_percent(800.0) == 100.0
    assert normalize_cpu_percent(0.0) == 0.0


def test_normalize_falls_back_when_cpu_count_missing(monkeypatch):
    monkeypatch.setattr(
        "core.system_monitor.psutil.cpu_count",
        lambda logical=True: None,
    )
    assert normalize_cpu_percent(42.0) == 42.0


def test_normalize_never_negative():
    assert normalize_cpu_percent(-1.0) == 0.0
