"""
process_page.py
Trang Process Manager: danh sách toàn bộ process, tìm kiếm, sắp xếp theo
CPU/RAM/Tên, lọc riêng process "cần chú ý", và kết thúc tiến trình với
xác nhận + bảo vệ whitelist (không cho kill process hệ thống lõi).
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

import psutil

from core.process_utils import scan_all_processes, FullProcessInfo
from core.privileged import elevated_kill

REFRESH_INTERVAL_MS = 5000  # quét chậm — scan toàn bộ process rất nặng (~100ms+)
MAX_ROWS_DISPLAYED = 150    # tránh treo UI khi máy có quá nhiều process


class ProcessPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._sort_key = "cpu"
        self._only_flagged = False
        self._all_processes: list[FullProcessInfo] = []

        # ---------- Thanh công cụ ----------
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_property("placeholder-text", "Tìm theo tên hoặc PID...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", lambda _e: self._render_list())
        toolbar.append(self.search_entry)

        toolbar.append(Gtk.Label(label="Sắp xếp:"))

        self.sort_dropdown = Gtk.DropDown.new_from_strings(["CPU", "RAM", "Tên"])
        self.sort_dropdown.connect("notify::selected", self._on_sort_changed)
        toolbar.append(self.sort_dropdown)

        self.flagged_toggle = Gtk.ToggleButton(label="Chỉ hiện process cần chú ý")
        self.flagged_toggle.connect("toggled", self._on_flagged_toggled)
        toolbar.append(self.flagged_toggle)

        self.append(toolbar)

        # ---------- Ghi chú minh bạch về heuristic ----------
        info_label = Gtk.Label(
            label=(
                "\u201cCần chú ý\u201d là gợi ý dựa trên heuristic (zombie, mồ côi, binary đã bị xóa, "
                "chạy nền không cửa sổ nhưng tốn tài nguyên) — không phải công cụ chẩn đoán virus. "
                "Luôn kiểm tra kỹ tên process trước khi kết thúc."
            ),
            wrap=True,
            xalign=0,
        )
        info_label.add_css_class("dim-label")
        info_label.add_css_class("caption")
        self.append(info_label)

        self.count_label = Gtk.Label(xalign=0)
        self.count_label.add_css_class("dim-label")
        self.append(self.count_label)

        # ---------- Danh sách process ----------
        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class("boxed-list")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.listbox)
        scroller.set_vexpand(True)
        self.append(scroller)

        self._timer_id = None
        # Chỉ poll khi trang đang hiện — tránh đốt CPU khi đang ở Dashboard/Cleaner/...
        self.connect("map", self._on_mapped)
        self.connect("unmap", self._on_unmapped)

    # ---------- Nạp dữ liệu ----------

    def _on_mapped(self, *_args):
        if self._timer_id is not None:
            return
        self._refresh()
        self._timer_id = GLib.timeout_add(REFRESH_INTERVAL_MS, self._refresh)

    def _on_unmapped(self, *_args):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _refresh(self) -> bool:
        self._all_processes = scan_all_processes()
        self._render_list()
        return self._timer_id is not None

    def _on_sort_changed(self, dropdown, _pspec):
        idx = dropdown.get_selected()
        self._sort_key = ["cpu", "mem", "name"][idx]
        self._render_list()

    def _on_flagged_toggled(self, toggle):
        self._only_flagged = toggle.get_active()
        self._render_list()

    # ---------- Render danh sách ----------

    def _render_list(self):
        query = self.search_entry.get_text().strip().lower()

        items = self._all_processes
        if query:
            items = [
                p for p in items
                if query in p.name.lower() or query == str(p.pid)
            ]
        if self._only_flagged:
            items = [p for p in items if p.flags.any()]

        if self._sort_key == "cpu":
            items = sorted(items, key=lambda p: p.cpu_percent, reverse=True)
        elif self._sort_key == "mem":
            items = sorted(items, key=lambda p: p.mem_percent, reverse=True)
        else:
            items = sorted(items, key=lambda p: p.name.lower())

        self.count_label.set_text(
            f"{len(items)} / {len(self._all_processes)} tiến trình"
            + (f" (hiển thị {MAX_ROWS_DISPLAYED} đầu tiên)" if len(items) > MAX_ROWS_DISPLAYED else "")
        )

        child = self.listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt

        for proc in items[:MAX_ROWS_DISPLAYED]:
            self.listbox.append(self._build_row(proc))

    def _build_row(self, proc: FullProcessInfo) -> Gtk.Widget:
        row = Adw.ActionRow()
        row.set_title(GLib.markup_escape_text(proc.name))

        subtitle_parts = [f"PID {proc.pid}", proc.status]
        labels = proc.flags.labels()
        if labels:
            subtitle_parts.append(" + ".join(labels))
        row.set_subtitle("  •  ".join(subtitle_parts))

        stats_label = Gtk.Label(label=f"{proc.cpu_percent:.1f}% CPU   {proc.mem_mb:.0f} MB")
        stats_label.add_css_class("numeric")
        if proc.flags.any():
            stats_label.add_css_class("level-warning")
        row.add_suffix(stats_label)

        kill_btn = Gtk.Button(label="Kết thúc")
        kill_btn.add_css_class("destructive-action")
        kill_btn.set_valign(Gtk.Align.CENTER)
        if proc.protected:
            kill_btn.set_sensitive(False)
            kill_btn.set_tooltip_text("Tiến trình hệ thống được bảo vệ, không thể kết thúc")
        else:
            kill_btn.connect("clicked", self._on_kill_clicked, proc)
        row.add_suffix(kill_btn)

        return row

    # ---------- Logic kết thúc process (có xác nhận) ----------

    def _on_kill_clicked(self, _btn, proc: FullProcessInfo):
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f'Kết thúc tiến trình "{proc.name}" (PID {proc.pid})?',
            secondary_text="Dữ liệu chưa lưu trong tiến trình này có thể bị mất. Bạn có chắc chắn không?",
        )
        dialog.connect("response", self._on_kill_confirmed, proc)
        dialog.present()

    def _on_kill_confirmed(self, dialog, response, proc: FullProcessInfo):
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return
        try:
            target = psutil.Process(proc.pid)
            target.terminate()
            try:
                target.wait(timeout=2)
            except psutil.TimeoutExpired:
                target.kill()
            self._refresh()
        except psutil.NoSuchProcess:
            self._refresh()
        except psutil.AccessDenied:
            self._ask_elevated_kill(proc)

    def _ask_elevated_kill(self, proc: FullProcessInfo):
        """Không đủ quyền kill thông thường -> hỏi có muốn thử với quyền root (pkexec) không."""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f'Không đủ quyền để kết thúc "{proc.name}" (PID {proc.pid}).',
            secondary_text=(
                "Đây thường là process chạy bằng quyền root (ví dụ service hệ thống). "
                "Bạn có muốn thử lại với quyền quản trị không? Hệ thống sẽ hỏi mật khẩu qua hộp thoại polkit."
            ),
        )
        dialog.connect("response", self._on_elevated_kill_confirmed, proc)
        dialog.present()

    def _on_elevated_kill_confirmed(self, dialog, response, proc: FullProcessInfo):
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return
        ok, msg = elevated_kill(proc.pid)
        if not ok:
            self._show_error(f'Không thể kết thúc "{proc.name}" (PID {proc.pid}): {msg}')
        self._refresh()

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
