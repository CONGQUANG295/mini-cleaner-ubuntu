"""
dashboard_page.py
Trang Dashboard chính: hiển thị CPU / RAM / Disk / Network dạng thanh tiến trình
(progress bar) cập nhật real-time, và bảng Top 10 process chiếm tài nguyên nhiều nhất.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from core.system_monitor import SystemMonitor

REFRESH_INTERVAL_MS = 2000  # cập nhật mỗi 2 giây (đủ mượt, đỡ tốn CPU)


def _level_css_class(percent: float) -> str:
    """Trả về class CSS tương ứng mức độ sử dụng: xanh / vàng / đỏ."""
    if percent >= 85:
        return "level-danger"
    if percent >= 60:
        return "level-warning"
    return "level-ok"


class StatCard(Gtk.Box):
    """Một 'thẻ' hiển thị 1 chỉ số: tiêu đề, thanh progress, và dòng chữ chi tiết."""

    def __init__(self, title: str, icon_name: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("card")
        self.add_css_class("stat-card")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(20)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("heading")
        header.append(icon)
        header.append(label)
        header.set_margin_start(12)
        header.set_margin_top(10)

        self.progress = Gtk.ProgressBar()
        self.progress.set_margin_start(12)
        self.progress.set_margin_end(12)
        self.progress.set_show_text(False)

        self.detail_label = Gtk.Label(label="—", xalign=0)
        self.detail_label.add_css_class("dim-label")
        self.detail_label.set_margin_start(12)
        self.detail_label.set_margin_bottom(10)

        self.append(header)
        self.append(self.progress)
        self.append(self.detail_label)

    def update(self, fraction: float, detail_text: str):
        self.progress.set_fraction(max(0.0, min(1.0, fraction)))
        self.detail_label.set_text(detail_text)

        for cls in ("level-ok", "level-warning", "level-danger"):
            self.progress.remove_css_class(cls)
        self.progress.add_css_class(_level_css_class(fraction * 100))


class DashboardPage(Gtk.Box):
    """Trang tổng quan: 4 thẻ chỉ số + bảng top process."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self.monitor = None  # tạo khi trang map lần đầu — tránh warm process lúc khởi động

        # --- Hàng thẻ chỉ số ---
        cards_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, homogeneous=True)
        self.cpu_card = StatCard("CPU", "speedometer-symbolic")
        self.mem_card = StatCard("RAM", "media-memory-symbolic")
        self.mem_card.set_tooltip_text(
            "Tính theo bộ nhớ khả dụng thực tế (total − available), giống cột "
            "\"available\" của lệnh `free -h`. Có thể thấp hơn con số htop hiển thị "
            "vì htop mặc định gộp cả cache/buffer có thể thu hồi ngay vào \"đang dùng\" "
            "— cả hai đều đúng, chỉ khác định nghĩa."
        )
        self.disk_card = StatCard("Ổ đĩa", "drive-harddisk-symbolic")
        self.net_card = StatCard("Mạng", "network-transmit-receive-symbolic")

        for card in (self.cpu_card, self.mem_card, self.disk_card, self.net_card):
            cards_row.append(card)
        self.append(cards_row)

        # --- Bảng Top Process ---
        section_label = Gtk.Label(label="Top Process đang chiếm tài nguyên", xalign=0)
        section_label.add_css_class("title-4")
        section_label.set_margin_top(8)
        self.append(section_label)

        self.process_list = Gtk.ListBox()
        self.process_list.add_css_class("boxed-list")
        self.process_list.set_selection_mode(Gtk.SelectionMode.NONE)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.process_list)
        scroller.set_vexpand(True)
        scroller.set_min_content_height(280)
        self.append(scroller)

        self._prev_net_recv = None
        self._prev_net_sent = None
        self._timer_id = None

        # Chỉ poll khi trang đang hiện — tránh quét process nền khi đang ở tab khác
        self.connect("map", self._on_mapped)
        self.connect("unmap", self._on_unmapped)

    def _on_mapped(self, *_args):
        if self._timer_id is not None:
            return
        if self.monitor is None:
            self.monitor = SystemMonitor()
        self._refresh()
        self._timer_id = GLib.timeout_add(REFRESH_INTERVAL_MS, self._refresh)

    def _on_unmapped(self, *_args):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _refresh(self) -> bool:
        """Được GLib gọi định kỳ. Return True để tiếp tục lặp lại."""
        snap = self.monitor.get_snapshot()

        self.cpu_card.update(
            snap.cpu_percent / 100,
            f"{snap.cpu_percent:.1f}% đang sử dụng",
        )
        self.mem_card.update(
            snap.mem_percent / 100,
            f"{snap.mem_used_gb:.1f} GB / {snap.mem_total_gb:.1f} GB",
        )
        self.disk_card.update(
            snap.disk_percent / 100,
            f"{snap.disk_used_gb:.1f} GB / {snap.disk_total_gb:.1f} GB",
        )

        # Network hiển thị dạng tốc độ tức thời (delta giữa 2 lần đo)
        if self._prev_net_recv is not None:
            delta_recv = max(0.0, snap.net_recv_mb - self._prev_net_recv)
            delta_sent = max(0.0, snap.net_sent_mb - self._prev_net_sent)
            speed_kb_s = (delta_recv + delta_sent) * 1024 / (REFRESH_INTERVAL_MS / 1000)
            fraction = min(1.0, speed_kb_s / 5000)  # 5MB/s coi như "đầy" thanh bar
            self.net_card.update(
                fraction,
                f"↓{delta_recv*1024:.0f} KB  ↑{delta_sent*1024:.0f} KB /{REFRESH_INTERVAL_MS/1000:.0f}s",
            )
        self._prev_net_recv = snap.net_recv_mb
        self._prev_net_sent = snap.net_sent_mb

        self._refresh_process_list()
        return self._timer_id is not None

    def _refresh_process_list(self):
        # Xóa danh sách cũ
        child = self.process_list.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.process_list.remove(child)
            child = next_child

        top_procs = self.monitor.get_top_processes(limit=10, sort_by="cpu")

        for proc in top_procs:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(proc.name))
            row.set_subtitle(f"PID {proc.pid}  •  {proc.mem_mb:.0f} MB RAM")

            cpu_label = Gtk.Label(label=f"{proc.cpu_percent:.1f}% CPU")
            cpu_label.add_css_class("numeric")
            # Ngưỡng theo % tổng cores (trước đây là per-core nên số cao hơn nhiều)
            if proc.cpu_percent >= 25:
                cpu_label.add_css_class("level-danger")
            elif proc.cpu_percent >= 10:
                cpu_label.add_css_class("level-warning")

            row.add_suffix(cpu_label)
            self.process_list.append(row)
