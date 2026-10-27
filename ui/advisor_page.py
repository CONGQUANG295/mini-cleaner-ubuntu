"""
advisor_page.py
Trang Tối ưu hệ thống (Giai đoạn 4):
  1. Gợi ý thông minh dựa trên ngưỡng tài nguyên hiện tại (RAM/CPU)
  2. Danh sách app khởi động cùng hệ thống — bật/tắt qua switch
  3. Danh sách systemd user-service đang bật — bật/tắt qua switch

Toàn bộ thao tác ở trang này KHÔNG cần quyền root và LUÔN có thể đảo ngược
(bật lại bất cứ lúc nào) — khác với Process Manager (kill) hay Cleaner (xóa file).
"""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from core.system_monitor import SystemMonitor
from core import autostart_utils as autostart

RAM_SUGGESTION_THRESHOLD = 70.0  # % RAM để bắt đầu gợi ý tắt bớt


class AdvisorPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        # Chỉ cần snapshot RAM — không warm toàn bộ process (rất tốn lúc mở app)
        self.monitor = SystemMonitor(warm_processes=False)

        # ---------- Gợi ý thông minh ----------
        self.suggestion_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.suggestion_box.add_css_class("card")
        self.suggestion_box.set_margin_bottom(4)

        self.suggestion_label = Gtk.Label(wrap=True, xalign=0)
        self.suggestion_label.set_margin_top(10)
        self.suggestion_label.set_margin_bottom(10)
        self.suggestion_label.set_margin_start(12)
        self.suggestion_label.set_margin_end(12)
        self.suggestion_box.append(self.suggestion_label)
        self.append(self.suggestion_box)

        # ---------- Section: Autostart apps ----------
        autostart_label = Gtk.Label(label="Ứng dụng khởi động cùng hệ thống", xalign=0)
        autostart_label.add_css_class("title-4")
        self.append(autostart_label)

        note1 = Gtk.Label(
            label="Tắt ở đây chỉ ngăn app tự chạy ở lần đăng nhập tiếp theo — có thể bật lại bất cứ lúc nào, không xóa gì cả.",
            wrap=True, xalign=0,
        )
        note1.add_css_class("dim-label")
        note1.add_css_class("caption")
        self.append(note1)

        self.autostart_list = Gtk.ListBox()
        self.autostart_list.add_css_class("boxed-list")
        self.autostart_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.append(self.autostart_list)

        # ---------- Section: User services ----------
        services_label = Gtk.Label(label="Dịch vụ nền đang bật (systemd --user)", xalign=0)
        services_label.add_css_class("title-4")
        services_label.set_margin_top(8)
        self.append(services_label)

        note2 = Gtk.Label(
            label="Tắt sẽ dừng dịch vụ ngay lập tức và không tự chạy lại lần sau — bật lại được bất cứ lúc nào.",
            wrap=True, xalign=0,
        )
        note2.add_css_class("dim-label")
        note2.add_css_class("caption")
        self.append(note2)

        services_scroller = Gtk.ScrolledWindow()
        self.services_list = Gtk.ListBox()
        self.services_list.add_css_class("boxed-list")
        self.services_list.set_selection_mode(Gtk.SelectionMode.NONE)
        services_scroller.set_child(self.services_list)
        services_scroller.set_vexpand(True)
        self.append(services_scroller)

        self._scanned = False
        self.connect("map", self._on_mapped)

    # ---------- Quét (chạy nền) ----------

    def _on_mapped(self, *_args):
        if self._scanned:
            return
        self._scanned = True
        self._start_scan()

    def _start_scan(self):
        self.suggestion_label.set_text("Đang phân tích hệ thống...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        snap = self.monitor.get_snapshot()
        autostart_entries = autostart.scan_autostart_apps()
        service_entries = autostart.scan_user_services()
        GLib.idle_add(self._on_scan_done, snap, autostart_entries, service_entries)

    def _on_scan_done(self, snap, autostart_entries, service_entries):
        self._render_suggestion(snap, autostart_entries, service_entries)
        self._render_autostart(autostart_entries)
        self._render_services(service_entries)
        return False

    # ---------- Gợi ý thông minh ----------

    def _render_suggestion(self, snap, autostart_entries, service_entries):
        enabled_apps = [e for e in autostart_entries if e.enabled]
        total_startup_items = len(enabled_apps) + len(service_entries)

        for cls in ("level-ok", "level-warning", "level-danger"):
            self.suggestion_label.remove_css_class(cls)

        if snap.mem_percent >= RAM_SUGGESTION_THRESHOLD and total_startup_items > 0:
            self.suggestion_label.set_text(
                f"⚠️ RAM đang dùng {snap.mem_percent:.0f}%. Bạn có {len(enabled_apps)} ứng dụng khởi động "
                f"cùng hệ thống và {len(service_entries)} dịch vụ nền đang bật. Cân nhắc tắt bớt các mục "
                f"ít dùng ở danh sách bên dưới để giải phóng RAM."
            )
            self.suggestion_label.add_css_class("level-warning")
        elif total_startup_items > 8:
            self.suggestion_label.set_text(
                f"💡 Bạn có khá nhiều mục khởi động cùng hệ thống ({len(enabled_apps)} app + "
                f"{len(service_entries)} service). Hệ thống hiện vẫn ổn ({snap.mem_percent:.0f}% RAM), "
                f"nhưng nếu thấy máy khởi động chậm, đây là nơi đáng xem đầu tiên."
            )
        else:
            self.suggestion_label.set_text(
                f"✅ Hệ thống đang ổn — RAM {snap.mem_percent:.0f}%, {len(enabled_apps)} app + "
                f"{len(service_entries)} service khởi động cùng hệ thống. Không có gì cần lo lắng."
            )
            self.suggestion_label.add_css_class("level-ok")

    # ---------- Render danh sách autostart apps ----------

    def _render_autostart(self, entries: list):
        child = self.autostart_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.autostart_list.remove(child)
            child = nxt

        if not entries:
            row = Adw.ActionRow(title="Không tìm thấy ứng dụng khởi động cùng hệ thống nào")
            self.autostart_list.append(row)
            return

        for entry in entries:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(entry.name))
            subtitle = entry.comment if entry.comment else entry.exec_cmd
            row.set_subtitle(GLib.markup_escape_text(subtitle[:80]))

            switch = Gtk.Switch()
            switch.set_active(entry.enabled)
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("state-set", self._on_autostart_toggled, entry)
            row.add_suffix(switch)

            self.autostart_list.append(row)

    def _on_autostart_toggled(self, switch, state, entry):
        ok, msg = autostart.set_autostart_enabled(entry, state)
        if not ok:
            self._show_error(f'Không thể cập nhật "{entry.name}": {msg}')
            return True  # giữ nguyên trạng thái switch cũ khi lỗi
        return False  # False = cho phép GTK tự cập nhật trạng thái switch

    # ---------- Render danh sách user services ----------

    def _render_services(self, entries: list):
        child = self.services_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.services_list.remove(child)
            child = nxt

        if not entries:
            row = Adw.ActionRow(title="Không có systemd user-service nào đang bật")
            self.services_list.append(row)
            return

        for entry in entries:
            row = Adw.ActionRow()
            row.set_title(GLib.markup_escape_text(entry.name))

            switch = Gtk.Switch()
            switch.set_active(entry.enabled)
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("state-set", self._on_service_toggled, entry)
            row.add_suffix(switch)

            self.services_list.append(row)

    def _on_service_toggled(self, switch, state, entry):
        ok, msg = autostart.set_user_service_enabled(entry.name, state)
        if not ok:
            self._show_error(f'Không thể cập nhật "{entry.name}": {msg}')
            return True
        return False

    # ---------- Tiện ích ----------

    def _show_error(self, message: str):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message,
        )
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.present()
