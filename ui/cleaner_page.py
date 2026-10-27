"""
cleaner_page.py
Trang Dọn dẹp rác: quét dung lượng từng loại rác hệ thống chạy trong
background thread (tránh treo UI), hiển thị checkbox để người dùng chọn,
xác nhận rồi mới xóa thật. Mục cần quyền root được xử lý qua pkexec
(core/privileged.py); mục không cần root xử lý trực tiếp
(core/junk_scanner.py).

Kernel cũ CHỈ hiển thị thông tin — không có nút xóa tự động (xem lý do
trong core/junk_scanner.py).
"""

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Pango

from core import junk_scanner as scanner
from core import privileged


# id -> (hàm dọn khi requires_root=False, hàm dọn qua pkexec khi requires_root=True)
CLEAN_ACTIONS = {
    "apt_cache": ("root", privileged.clean_apt_cache),
    "thumbnails": ("local", scanner.clean_thumbnails),
    "trash": ("local", scanner.clean_trash),
    "crash": ("root", privileged.clean_crash_reports),
    "journal": ("root", privileged.vacuum_journal),
    "user_tmp": ("local", scanner.clean_user_tmp),
}


def _info_labels(title: str, path_hint: str) -> Gtk.Box:
    """Cột chữ: title + path; path wrap để không bị cắt khi hẹp."""
    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    title_label = Gtk.Label(label=title, xalign=0)
    title_label.add_css_class("heading")
    title_label.set_wrap(True)
    title_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    path_label = Gtk.Label(label=path_hint, xalign=0)
    path_label.add_css_class("dim-label")
    path_label.add_css_class("caption")
    path_label.set_wrap(True)
    path_label.set_wrap_mode(Pango.WrapMode.CHAR)
    path_label.set_hexpand(True)
    text_box.append(title_label)
    text_box.append(path_label)
    text_box.set_hexpand(True)
    return text_box


def _size_label(num_bytes: int) -> Gtk.Label:
    label = Gtk.Label(label=scanner.human_size(num_bytes))
    label.add_css_class("numeric")
    label.set_valign(Gtk.Align.CENTER)
    label.set_halign(Gtk.Align.END)
    label.set_xalign(1.0)
    label.set_width_chars(12)
    label.set_hexpand(False)
    return label


class CleanerRow(Gtk.Box):
    """Một dòng: checkbox + tên + đường dẫn + dung lượng + badge 'cần quyền root'."""

    def __init__(self, category: scanner.JunkCategory):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.category = category
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.set_hexpand(True)

        self.checkbox = Gtk.CheckButton()
        self.checkbox.set_valign(Gtk.Align.CENTER)
        self.append(self.checkbox)

        self.append(_info_labels(category.title, category.path_hint))

        if category.requires_root:
            root_badge = Gtk.Label(label="cần quyền root")
            root_badge.add_css_class("dim-label")
            root_badge.add_css_class("caption")
            root_badge.set_valign(Gtk.Align.CENTER)
            root_badge.set_hexpand(False)
            self.append(root_badge)

        self.append(_size_label(category.size_bytes))

        # Không có gì để dọn -> không cho chọn, tránh thao tác thừa
        if category.size_bytes <= 0:
            self.checkbox.set_sensitive(False)


class DevToolsCleanerGroup(Gtk.Box):
    """Khối gộp cache công cụ lập trình: checkbox cha + expander + checkbox con."""

    def __init__(self, tools: list[scanner.DevToolCache], on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._tools = tools
        self._on_change = on_change
        self._syncing = False
        self._child_checks: list[tuple[scanner.DevToolCache, Gtk.CheckButton]] = []

        ids_hint = ", ".join(t.id for t in tools)
        total = sum(t.size_bytes for t in tools)

        self.set_hexpand(True)

        parent_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        parent_row.set_margin_top(4)
        parent_row.set_margin_bottom(4)
        parent_row.set_hexpand(True)

        self.parent_check = Gtk.CheckButton()
        self.parent_check.set_active(True)
        self.parent_check.set_valign(Gtk.Align.CENTER)
        self.parent_check.connect("toggled", self._on_parent_toggled)
        parent_row.append(self.parent_check)

        parent_row.append(_info_labels("Cache công cụ lập trình", ids_hint))

        self.size_label = _size_label(total)
        parent_row.append(self.size_label)
        self.append(parent_row)

        expander = Gtk.Expander(label="Chi tiết từng công cụ")
        expander.set_expanded(True)
        expander.set_hexpand(True)
        child_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        child_box.set_margin_start(28)
        child_box.set_hexpand(True)

        for tool in tools:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_margin_top(2)
            row.set_margin_bottom(2)
            row.set_hexpand(True)
            check = Gtk.CheckButton()
            check.set_active(True)
            check.set_valign(Gtk.Align.CENTER)
            check.connect("toggled", self._on_child_toggled)
            row.append(check)

            row.append(_info_labels(tool.title, tool.path_hint))
            row.append(_size_label(tool.size_bytes))

            child_box.append(row)
            self._child_checks.append((tool, check))

        expander.set_child(child_box)
        self.append(expander)
        self._refresh_size_label()

    def _on_parent_toggled(self, _check):
        if self._syncing:
            return
        self._syncing = True
        active = self.parent_check.get_active()
        for _tool, check in self._child_checks:
            check.set_active(active)
        self._syncing = False
        self._refresh_size_label()
        self._on_change()

    def _on_child_toggled(self, _check):
        if self._syncing:
            return
        self._syncing = True
        all_on = all(check.get_active() for _tool, check in self._child_checks)
        self.parent_check.set_active(all_on)
        self._syncing = False
        self._refresh_size_label()
        self._on_change()

    def _refresh_size_label(self):
        self.size_label.set_text(scanner.human_size(self.selected_bytes()))

    def selected_tools(self) -> list[scanner.DevToolCache]:
        return [tool for tool, check in self._child_checks if check.get_active()]

    def selected_bytes(self) -> int:
        return sum(tool.size_bytes for tool in self.selected_tools())

    def has_selection(self) -> bool:
        return len(self.selected_tools()) > 0


class CleanerPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._rows: list[CleanerRow] = []
        self._orphan_pkg_names: list[str] = []
        self._dev_group: DevToolsCleanerGroup | None = None

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label="Dọn dẹp rác hệ thống", xalign=0)
        title.add_css_class("title-4")
        title.set_hexpand(True)
        header_row.append(title)

        self.rescan_btn = Gtk.Button(label="Quét lại")
        self.rescan_btn.connect("clicked", lambda _b: self._start_scan())
        header_row.append(self.rescan_btn)
        self.append(header_row)

        self.status_label = Gtk.Label(label="Đang quét lần đầu...", xalign=0)
        self.status_label.add_css_class("dim-label")
        self.append(self.status_label)

        self.spinner = Gtk.Spinner()
        self.append(self.spinner)

        self.rows_box = Gtk.ListBox()
        self.rows_box.add_css_class("boxed-list")
        self.rows_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.rows_box)
        scroller.set_vexpand(True)
        self.append(scroller)

        # ---------- Thông tin kernel cũ (chỉ đọc) ----------
        self.kernel_label = Gtk.Label(wrap=True, xalign=0)
        self.kernel_label.add_css_class("dim-label")
        self.kernel_label.add_css_class("caption")
        self.append(self.kernel_label)

        # ---------- Thanh hành động ----------
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.total_label = Gtk.Label(label="", xalign=0)
        self.total_label.set_hexpand(True)
        action_row.append(self.total_label)

        self.clean_btn = Gtk.Button(label="Dọn các mục đã chọn")
        self.clean_btn.add_css_class("destructive-action")
        self.clean_btn.connect("clicked", self._on_clean_clicked)
        self.clean_btn.set_sensitive(False)
        action_row.append(self.clean_btn)
        self.append(action_row)

        self._start_scan()

    # ---------- Quét (chạy nền để không treo UI) ----------

    def _start_scan(self):
        self.status_label.set_text("Đang quét dung lượng rác (có thể mất vài giây)...")
        self.spinner.start()
        self.clean_btn.set_sensitive(False)
        self.rescan_btn.set_sensitive(False)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        categories = [
            scanner.scan_apt_cache(),
            scanner.scan_thumbnails(),
            scanner.scan_trash(),
            scanner.scan_crash_reports(),
            scanner.scan_journal_logs(),
            scanner.scan_user_tmp(),
        ]
        orphan_cat, orphan_names = scanner.scan_orphan_packages()
        categories.append(orphan_cat)
        current_kernel, all_kernels = scanner.scan_old_kernels()
        dev_tools = scanner.scan_dev_tool_caches()

        GLib.idle_add(
            self._on_scan_done,
            categories,
            orphan_names,
            current_kernel,
            all_kernels,
            dev_tools,
        )

    def _on_scan_done(
        self, categories, orphan_names, current_kernel, all_kernels, dev_tools
    ):
        self._orphan_pkg_names = orphan_names

        child = self.rows_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.rows_box.remove(child)
            child = nxt
        self._rows = []
        self._dev_group = None

        for cat in categories:
            row = CleanerRow(cat)
            row.checkbox.connect("toggled", lambda _c: self._update_total())
            self._rows.append(row)
            self.rows_box.append(row)

        # Cùng boxed-list với các mục khác — tránh nhìn lạc loài ngoài khung trắng
        if dev_tools:
            self._dev_group = DevToolsCleanerGroup(dev_tools, self._update_total)
            self.rows_box.append(self._dev_group)

        other_kernels = [k for k in all_kernels if current_kernel not in k]
        if other_kernels:
            self.kernel_label.set_text(
                f"Kernel đang chạy: {current_kernel}. Kernel cũ khác đã cài: "
                f"{', '.join(other_kernels)}. "
                "App không tự xóa kernel để tránh rủi ro — nếu muốn dọn, kiểm tra kỹ rồi chạy thủ công: "
                f"sudo apt remove <tên-gói-kernel-cũ>"
            )
        else:
            self.kernel_label.set_text(
                f"Kernel đang chạy: {current_kernel}. Không có kernel cũ nào khác."
            )

        self.spinner.stop()
        self.status_label.set_text("Quét xong. Chọn các mục muốn dọn rồi bấm nút bên dưới.")
        self.rescan_btn.set_sensitive(True)
        self._update_total()
        return False  # GLib.idle_add: chạy 1 lần rồi thôi

    # ---------- Tính tổng dung lượng đã chọn ----------

    def _update_total(self):
        selected = [r for r in self._rows if r.checkbox.get_active()]
        total = sum(r.category.size_bytes for r in selected)
        count = len(selected)
        if self._dev_group and self._dev_group.has_selection():
            tools = self._dev_group.selected_tools()
            total += sum(t.size_bytes for t in tools)
            count += len(tools)
        if count:
            self.total_label.set_text(
                f"Đã chọn {count} mục — {scanner.human_size(total)}"
            )
        else:
            self.total_label.set_text("Chưa chọn mục nào")
        self.clean_btn.set_sensitive(count > 0)

    # ---------- Dọn dẹp thật ----------

    def _on_clean_clicked(self, _btn):
        selected = [r for r in self._rows if r.checkbox.get_active()]
        selected_tools = (
            self._dev_group.selected_tools() if self._dev_group else []
        )
        if not selected and not selected_tools:
            return

        names = [f"• {r.category.title}" for r in selected]
        names.extend(f"• {t.title}" for t in selected_tools)
        total = sum(r.category.size_bytes for r in selected) + sum(
            t.size_bytes for t in selected_tools
        )
        needs_root = any(r.category.requires_root for r in selected)

        secondary = f"Sẽ dọn khoảng {scanner.human_size(total)}.\n" + "\n".join(names)
        if needs_root:
            secondary += (
                "\n\nMột số mục cần quyền quản trị — hệ thống sẽ hỏi mật khẩu "
                "qua hộp thoại polkit."
            )

        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Xác nhận dọn dẹp?",
            secondary_text=secondary,
        )
        dialog.connect(
            "response", self._on_clean_confirmed, selected, selected_tools
        )
        dialog.present()

    def _on_clean_confirmed(
        self,
        dialog,
        response,
        selected: list[CleanerRow],
        selected_tools: list[scanner.DevToolCache],
    ):
        dialog.destroy()
        if response != Gtk.ResponseType.YES:
            return

        self.status_label.set_text("Đang dọn dẹp...")
        self.spinner.start()
        self.clean_btn.set_sensitive(False)
        threading.Thread(
            target=self._clean_worker,
            args=(selected, selected_tools),
            daemon=True,
        ).start()

    def _clean_worker(
        self,
        selected: list[CleanerRow],
        selected_tools: list[scanner.DevToolCache],
    ):
        results = []
        for row in selected:
            kind, action = CLEAN_ACTIONS.get(row.category.id, (None, None))
            if action is None:
                # Package mồ côi xử lý riêng vì cần chạy autoremove, không phải xóa file
                if row.category.id == "orphan_pkgs":
                    ok, msg = privileged.autoremove_packages()
                else:
                    ok, msg = False, "Không có hành động dọn cho mục này"
            else:
                ok, msg = action()
            results.append((row.category.title, ok, msg))

        for tool in selected_tools:
            ok, msg = scanner.clean_dev_tool_cache(tool)
            results.append((tool.title, ok, msg))

        GLib.idle_add(self._on_clean_done, results)

    def _on_clean_done(self, results):
        self.spinner.stop()
        lines = []
        for title, ok, msg in results:
            icon = "✅" if ok else "❌"
            lines.append(f"{icon} {title}: {msg}")

        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Kết quả dọn dẹp",
            secondary_text="\n".join(lines),
        )
        dialog.connect("response", lambda d, _r: d.destroy())
        dialog.present()

        self._start_scan()  # quét lại để cập nhật dung lượng mới
        return False
