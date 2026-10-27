"""
process_utils.py
Quét toàn bộ process đang chạy và gắn cờ những process "cần chú ý" theo
4 tiêu chí RÕ RÀNG, dựa trên dữ liệu hợp lệ từ /proc và psutil:

  1. Zombie      - process đã chết nhưng chưa được cha "thu dọn" (wait())
  2. Mồ côi      - cha đã chết, bị hệ thống gán lại cho init (ppid=1),
                   và KHÔNG nằm trong danh sách daemon hệ thống hợp lệ
  3. Binary xóa  - file thực thi gốc đã bị xóa khỏi đĩa nhưng process vẫn
                   chạy trong RAM (thường gặp sau khi update phần mềm
                   nhưng chưa restart lại app/service liên quan)
  4. Không cửa sổ - process không sở hữu cửa sổ nào đang hiển thị NHƯNG
                   đang tiêu tốn CPU/RAM đáng kể (cần cài `wmctrl` để bật
                   tính năng này, sẽ tự bỏ qua nếu chưa cài)

QUAN TRỌNG: đây là heuristic mang tính gợi ý để người dùng để ý, KHÔNG PHẢI
công cụ chẩn đoán virus/rootkit/malware. Luôn hiển thị rõ điều này trên UI.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass, field

import psutil

from core.system_monitor import normalize_cpu_percent
from core.whitelist import is_protected

# Ngưỡng tài nguyên để coi 1 process "không cửa sổ" là đáng chú ý
# (tránh gắn cờ tràn lan mọi daemon nền bình thường, vốn vốn dĩ không có cửa sổ)
# CPU threshold tính theo raw psutil (per-core, giống top) trước khi normalize hiển thị.
NO_WINDOW_CPU_THRESHOLD = 3.0     # % của 1 logical core
NO_WINDOW_MEM_MB_THRESHOLD = 150  # MB


@dataclass
class HiddenFlags:
    zombie: bool = False
    orphan: bool = False
    deleted_binary: bool = False
    no_window: bool = False

    def any(self) -> bool:
        return self.zombie or self.orphan or self.deleted_binary or self.no_window

    def labels(self) -> list[str]:
        out = []
        if self.zombie:
            out.append("Zombie")
        if self.orphan:
            out.append("Mồ côi")
        if self.deleted_binary:
            out.append("Binary đã xóa")
        if self.no_window:
            out.append("Nền không cửa sổ")
        return out


@dataclass
class FullProcessInfo:
    pid: int
    ppid: int
    name: str
    cpu_percent: float
    mem_percent: float
    mem_mb: float
    status: str
    protected: bool
    flags: HiddenFlags = field(default_factory=HiddenFlags)


def _get_windowed_pids() -> set[int] | None:
    """
    Trả về tập PID đang sở hữu ít nhất 1 cửa sổ hiển thị, dùng lệnh `wmctrl`.
    Trả None nếu wmctrl chưa được cài, HOẶC nếu đang chạy dưới phiên Wayland
    thuần (không qua XWayland) — vì `wmctrl` dựa trên giao thức X11
    (_NET_CLIENT_LIST) nên không thấy được cửa sổ Wayland gốc. Từ Ubuntu 26.04
    trở đi, phiên GNOME mặc định chỉ còn Wayland (không còn tùy chọn đăng nhập
    X11), nên nếu không kiểm tra điều này, wmctrl sẽ trả về danh sách rỗng và
    khiến app hiểu nhầm MỌI process là "không cửa sổ" — báo động giả hàng loạt.
    """
    if shutil.which("wmctrl") is None:
        return None
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return None
    try:
        result = subprocess.run(
            ["wmctrl", "-lp"], capture_output=True, text=True, timeout=2
        )
        pids = set()
        for line in result.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 3:
                try:
                    pids.add(int(parts[2]))
                except ValueError:
                    continue
        return pids
    except Exception:
        return None


def _has_deleted_binary(pid: int) -> bool:
    """Kiểm tra /proc/<pid>/exe có trỏ tới file đã bị xóa hay không."""
    try:
        link_target = os.readlink(f"/proc/{pid}/exe")
        return "(deleted)" in link_target
    except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
        return False


def _is_systemd_managed(pid: int) -> bool:
    """
    Kiểm tra process có đang được systemd quản lý như một unit hợp lệ hay không,
    bằng cách đọc /proc/<pid>/cgroup. Trên hệ thống dùng systemd (mọi Ubuntu hiện đại),
    systemd (PID 1) là cha trực tiếp của HẦU HẾT mọi service — dockerd, rsyslogd,
    wpa_supplicant... — nên ppid=1 là bình thường, KHÔNG phải dấu hiệu "mồ côi".

    Nếu process nằm trong 1 cgroup có tên .service/.scope/.socket/.mount, tức nó
    đang được systemd track như 1 unit thật sự -> coi là hợp lệ, không gắn cờ.
    Chỉ những process có ppid=1 nhưng KHÔNG thuộc bất kỳ unit nào (process trôi nổi
    thật sự, ví dụ chạy `nohup ... &` rồi terminal gốc bị đóng) mới bị gắn cờ mồ côi.
    """
    try:
        with open(f"/proc/{pid}/cgroup", "r") as f:
            content = f.read()
        return any(marker in content for marker in (".service", ".scope", ".socket", ".mount"))
    except (FileNotFoundError, PermissionError, OSError):
        # Không đọc được cgroup (thường do quyền) -> không đủ căn cứ để gắn cờ,
        # thà bỏ sót còn hơn báo động giả
        return True


def scan_all_processes() -> list[FullProcessInfo]:
    """Quét toàn bộ process hệ thống, trả về danh sách kèm cờ 'cần chú ý'."""
    windowed_pids = _get_windowed_pids()
    results: list[FullProcessInfo] = []

    for p in psutil.process_iter(
        ["pid", "ppid", "name", "status", "memory_percent", "memory_info"]
    ):
        try:
            info = p.info
            pid = info["pid"]
            ppid = info["ppid"] or 0
            name = info["name"] or "?"
            status = info["status"]
            cpu_raw = p.cpu_percent(interval=None)
            cpu = normalize_cpu_percent(cpu_raw)
            mem_info = info["memory_info"]
            mem_mb = (mem_info.rss / (1024 ** 2)) if mem_info else 0.0
            mem_percent = info["memory_percent"] or 0.0

            protected = is_protected(name, pid)
            is_kernel_thread = name.startswith("[") and name.endswith("]")

            flags = HiddenFlags()
            flags.zombie = status == psutil.STATUS_ZOMBIE

            # Mồ côi: cha là init (ppid=1) NHƯNG không được systemd quản lý như 1 unit
            # hợp lệ (xem giải thích chi tiết ở _is_systemd_managed phía trên)
            flags.orphan = (
                ppid == 1
                and not protected
                and not is_kernel_thread
                and pid > 300
                and not _is_systemd_managed(pid)
            )

            flags.deleted_binary = (not is_kernel_thread) and _has_deleted_binary(pid)

            if windowed_pids is not None and not protected and not is_kernel_thread:
                consumes_significant = (
                    cpu_raw >= NO_WINDOW_CPU_THRESHOLD or mem_mb >= NO_WINDOW_MEM_MB_THRESHOLD
                )
                flags.no_window = pid not in windowed_pids and consumes_significant

            results.append(
                FullProcessInfo(
                    pid=pid,
                    ppid=ppid,
                    name=name,
                    cpu_percent=cpu,
                    mem_percent=mem_percent,
                    mem_mb=mem_mb,
                    status=status,
                    protected=protected,
                    flags=flags,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return results
