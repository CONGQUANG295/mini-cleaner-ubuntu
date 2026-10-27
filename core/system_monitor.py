"""
system_monitor.py
Lớp wrapper quanh psutil để lấy thông số CPU / RAM / Disk / Network
và danh sách top process đang chiếm tài nguyên nhiều nhất.

Toàn bộ hàm ở đây chỉ ĐỌC dữ liệu, không thực hiện thao tác nguy hiểm
(kill process, xóa file...) - những việc đó thuộc các module ở Giai đoạn 2, 3.
"""

import psutil
from dataclasses import dataclass


def normalize_cpu_percent(raw: float) -> float:
    """
    Đổi CPU% kiểu top (theo 1 logical core, có thể >100) sang % trên tổng
    toàn bộ logical cores (0–100 khi dùng hết máy).
    """
    if raw <= 0:
        return 0.0
    n_cpus = psutil.cpu_count(logical=True) or 1
    return raw / n_cpus


@dataclass
class SystemSnapshot:
    """Một 'lát cắt' thông số hệ thống tại thời điểm hiện tại."""
    cpu_percent: float
    mem_percent: float
    mem_used_gb: float
    mem_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    net_sent_mb: float
    net_recv_mb: float


@dataclass
class ProcessInfo:
    """Thông tin gọn của một tiến trình để hiển thị trong bảng Top Process."""
    pid: int
    name: str
    cpu_percent: float
    mem_percent: float
    mem_mb: float


class SystemMonitor:
    """
    Đối tượng duy trì trạng thái để tính CPU% chính xác theo thời gian
    (psutil cần gọi cpu_percent() hai lần cách nhau một khoảng để có số liệu đúng).
    """

    def __init__(self, warm_processes: bool = True):
        # "Làm nóng" bộ đo CPU percent - lần gọi đầu luôn trả về 0.0
        psutil.cpu_percent(interval=None)
        # warm_processes=False khi chỉ cần snapshot hệ thống (tránh duyệt ~hàng trăm PID lúc mở app)
        if warm_processes:
            for p in psutil.process_iter(["pid"]):
                try:
                    p.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

    def get_snapshot(self) -> SystemSnapshot:
        """Lấy thông số tổng quan CPU/RAM/Disk/Network hiện tại."""
        cpu = psutil.cpu_percent(interval=None)

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()

        return SystemSnapshot(
            cpu_percent=cpu,
            mem_percent=mem.percent,
            mem_used_gb=mem.used / (1024 ** 3),
            mem_total_gb=mem.total / (1024 ** 3),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 ** 3),
            disk_total_gb=disk.total / (1024 ** 3),
            net_sent_mb=net.bytes_sent / (1024 ** 2),
            net_recv_mb=net.bytes_recv / (1024 ** 2),
        )

    def get_top_processes(self, limit: int = 10, sort_by: str = "cpu") -> list[ProcessInfo]:
        """
        Trả về danh sách top process chiếm tài nguyên nhiều nhất.
        sort_by: "cpu" hoặc "mem"
        CPU% đã chuẩn hóa theo tổng logical cores (0–100 của cả máy).
        """
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_percent", "memory_info"]):
            try:
                cpu = normalize_cpu_percent(p.cpu_percent(interval=None))
                info = p.info
                mem_mb = (info["memory_info"].rss / (1024 ** 2)) if info["memory_info"] else 0.0
                procs.append(
                    ProcessInfo(
                        pid=info["pid"],
                        name=info["name"] or "?",
                        cpu_percent=cpu,
                        mem_percent=info["memory_percent"] or 0.0,
                        mem_mb=mem_mb,
                    )
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        key = (lambda x: x.cpu_percent) if sort_by == "cpu" else (lambda x: x.mem_percent)
        procs.sort(key=key, reverse=True)
        return procs[:limit]
