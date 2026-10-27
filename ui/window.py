"""
window.py
Cửa sổ chính của ứng dụng — cả 4 giai đoạn (Dashboard, Process Manager,
Dọn dẹp rác, Tối ưu hệ thống) đều đã hoạt động đầy đủ.

LƯU Ý TƯƠNG THÍCH: dùng Gtk.Paned (sidebar + content) thay vì
Adw.NavigationSplitView, vì NavigationSplitView chỉ có từ Libadwaita 1.4+
(Ubuntu 24.04+). Ubuntu 22.04 chỉ có Libadwaita 1.1.7 nên sẽ báo lỗi
"AttributeError: 'gi.repository.Adw' object has no attribute
'NavigationSplitView'" nếu dùng API mới. Gtk.Paned tương thích ngược,
chạy tốt trên cả hai phiên bản Ubuntu.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from ui.dashboard_page import DashboardPage
from ui.process_page import ProcessPage
from ui.cleaner_page import CleanerPage
from ui.advisor_page import AdvisorPage


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application):
        super().__init__(application=app, title="Mini Cleaner")
        # Rộng hơn để đủ chỗ cho path cache / cột dung lượng; chặn thu hẹp quá mức
        self.set_default_size(1100, 720)
        self.set_size_request(960, 560)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(230)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)
        paned.set_hexpand(True)
        paned.set_vexpand(True)
        self.set_content(paned)

        # ---------- Sidebar ----------
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_show_end_title_buttons(False)
        sidebar_header.set_title_widget(Adw.WindowTitle(title="Mini Cleaner"))
        sidebar_box.append(sidebar_header)

        self.nav_list = Gtk.ListBox()
        self.nav_list.add_css_class("navigation-sidebar")
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)

        self._nav_items = [
            ("Dashboard", "speedometer-symbolic"),
            ("Process Manager", "system-run-symbolic"),
            ("Dọn dẹp rác", "user-trash-symbolic"),
            ("Tối ưu hệ thống", "preferences-system-symbolic"),
        ]
        for title, icon_name in self._nav_items:
            row = Adw.ActionRow(title=title)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
            self.nav_list.append(row)

        sidebar_box.append(self.nav_list)
        paned.set_start_child(sidebar_box)

        # ---------- Content (đổi theo lựa chọn sidebar) ----------
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        self.content_stack.add_named(self._wrap_with_header(DashboardPage(), "Dashboard"), "dashboard")
        self.content_stack.add_named(self._wrap_with_header(ProcessPage(), "Process Manager"), "process")
        self.content_stack.add_named(self._wrap_with_header(CleanerPage(), "Dọn dẹp rác"), "cleaner")
        self.content_stack.add_named(self._wrap_with_header(AdvisorPage(), "Tối ưu hệ thống"), "advisor")

        paned.set_end_child(self.content_stack)
        paned.set_resize_end_child(True)

        self.nav_list.connect("row-selected", self._on_nav_selected)
        self.nav_list.select_row(self.nav_list.get_row_at_index(0))

    def _wrap_with_header(self, child: Gtk.Widget, title: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_hexpand(True)
        box.set_vexpand(True)
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=title))
        box.append(header)
        child.set_hexpand(True)
        child.set_vexpand(True)
        box.append(child)
        return box

    def _on_nav_selected(self, _listbox, row):
        if row is None:
            return
        index = row.get_index()
        keys = ["dashboard", "process", "cleaner", "advisor"]
        self.content_stack.set_visible_child_name(keys[index])
