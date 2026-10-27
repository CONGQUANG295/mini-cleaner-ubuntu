# Mini Cleaner — Đầy đủ 4 giai đoạn

Ứng dụng desktop native cho Ubuntu, xây bằng **Python + GTK4 + Libadwaita**.

- **Giai đoạn 1 (xong):** Dashboard hiển thị CPU / RAM / Disk / Network real-time
  và bảng Top 10 process chiếm tài nguyên nhiều nhất.
- **Giai đoạn 2 (xong):** Process Manager — danh sách toàn bộ process, tìm kiếm,
  sắp xếp theo CPU/RAM/Tên, phát hiện process "cần chú ý" (zombie, mồ côi thật sự,
  binary đã xóa, chạy nền không cửa sổ tốn tài nguyên), kết thúc tiến trình có xác
  nhận, whitelist bảo vệ process hệ thống lõi, và **thử lại với quyền quản trị qua
  pkexec** khi bị từ chối quyền.
- **Giai đoạn 3 (xong):** Dọn dẹp rác — quét dung lượng cache APT, thumbnail, Thùng
  rác, crash report, log hệ thống, file tạm của bạn, package mồ côi, và khối cache
  công cụ lập trình (npm/pnpm/yarn/bun/pip/cargo/go/flatpak, chọn từng tool);
  chọn mục cần dọn, xác nhận rồi mới xóa thật; kernel cũ chỉ hiển thị thông tin
  (không tự xóa vì rủi ro cao).
- **Giai đoạn 4 (xong):** Tối ưu hệ thống — gợi ý thông minh theo ngưỡng RAM/CPU,
  danh sách app khởi động cùng hệ thống (XDG Autostart) và systemd user-service
  đang bật, bật/tắt bằng switch — **không cần quyền root, luôn bật lại được**.

Cả 4 trang đều đã hoạt động đầy đủ — đây là bản MVP hoàn chỉnh của roadmap ban đầu.

## ⚠️ Ghi chú tương thích phiên bản Ubuntu

| Ubuntu | GTK4 | Libadwaita | Trạng thái |
|---|---|---|---|
| 22.04 LTS | 4.6 | 1.1.7 | ✅ Đã test tương thích — dùng `Gtk.Paned` thay vì `Adw.NavigationSplitView` |
| 24.04 LTS+ | 4.14+ | 1.5+ | ✅ Tương thích, có thể nâng cấp UI dùng `Adw.NavigationSplitView` nếu muốn |

Nếu bạn gặp lỗi `AttributeError: 'gi.repository.Adw' object has no attribute 'NavigationSplitView'`,
đó là do máy chạy Ubuntu 22.04 — code hiện tại đã fix sẵn bằng `Gtk.Paned`, không cần sửa gì thêm.

## 1. Cài đặt thư viện hệ thống (bắt buộc, chạy trên máy Ubuntu thật)

GTK4 + Libadwaita là binding hệ thống, **không cài được qua pip** — phải cài qua `apt`:

```bash
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 python3-pip
```

## 2. Cài thư viện Python

```bash
pip install -r requirements.txt --break-system-packages
```

(hoặc dùng virtualenv nếu bạn muốn tách môi trường — nhưng lưu ý virtualenv cần bật
`--system-site-packages` để thấy được `gi`, vì PyGObject là binding hệ thống)

## 3. Chạy thử

```bash
cd mini-cleaner
python3 main.py
```

Bạn sẽ thấy cửa sổ app hiện ra với sidebar bên trái và Dashboard đang chạy real-time.

## 4. (Tùy chọn) Cài wmctrl để bật tính năng phát hiện "process nền không cửa sổ"

```bash
sudo apt install -y wmctrl
```

Nếu không cài, app vẫn chạy bình thường — chỉ riêng nhãn "Nền không cửa sổ" trong
Process Manager sẽ không xuất hiện (3 nhãn còn lại: Zombie, Mồ côi, Binary đã xóa
vẫn hoạt động không cần wmctrl).

## 5. Quyền quản trị (pkexec) cho Process Manager & Dọn dẹp rác

Một số thao tác (kill process hệ thống, dọn cache APT, crash report, log, gỡ
package mồ côi) cần quyền root. App **không** chạy toàn bộ bằng `sudo` — thay vào
đó dùng `pkexec` để xin quyền root **chỉ cho đúng thao tác đó**, hệ thống sẽ tự
hiện hộp thoại xin mật khẩu qua polkit.

`pkexec` nằm trong gói `policykit-1`, **mặc định đã có sẵn** trên Ubuntu Desktop.
Nếu vì lý do nào đó chưa có:

```bash
sudo apt install -y policykit-1
```

## 6. Cấu trúc project

```
mini-cleaner/
├── main.py                  # Entry point
├── requirements.txt
├── ui/
│   ├── window.py             # Cửa sổ chính + sidebar điều hướng (Gtk.Paned)
│   ├── dashboard_page.py     # Trang Dashboard (Giai đoạn 1)
│   ├── process_page.py       # Trang Process Manager (Giai đoạn 2)
│   ├── cleaner_page.py       # Trang Dọn dẹp rác (Giai đoạn 3)
│   └── advisor_page.py       # Trang Tối ưu hệ thống (Giai đoạn 4)
├── core/
│   ├── system_monitor.py     # Wrapper quanh psutil cho Dashboard
│   ├── process_utils.py      # Quét process + phát hiện "cần chú ý"
│   ├── whitelist.py          # Danh sách process hệ thống được bảo vệ
│   ├── privileged.py         # Thao tác cần quyền root, thực hiện qua pkexec
│   ├── junk_scanner.py       # Quét dung lượng rác + dọn dẹp phần không cần root
│   └── autostart_utils.py    # Quét/bật/tắt autostart app + systemd user-service
├── resources/
│   └── style.css             # Màu sắc cảnh báo xanh/vàng/đỏ
└── packaging/
    └── mini-cleaner.desktop  # File để app xuất hiện trong menu ứng dụng
```

## 7. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `ValueError: Namespace Gtk not available` | Chưa cài `gir1.2-gtk-4.0` | Chạy lại lệnh apt ở bước 1 |
| `ModuleNotFoundError: No module named 'gi'` | Chưa cài `python3-gi`, hoặc đang dùng virtualenv không bật system-site-packages | Cài `python3-gi` qua apt, hoặc tạo venv với `--system-site-packages` |
| `AttributeError: ... no attribute 'NavigationSplitView'` | Ubuntu 22.04 chỉ có Libadwaita 1.1, chưa có API này | Đã fix sẵn trong code hiện tại bằng `Gtk.Paned` — cập nhật file mới nhất |
| `AttributeError: 'SearchEntry' object has no attribute 'set_placeholder_text'` | GTK4 không có method này (khác GTK3) | Đã fix — dùng `set_property("placeholder-text", ...)` trong code hiện tại |
| Gần như mọi process đều bị gắn nhãn "Mồ côi" | Bug cũ: coi `ppid==1` là mồ côi, nhưng trên systemd đó là bình thường | Đã fix — giờ kiểm tra qua `/proc/pid/cgroup` để chỉ gắn cờ process thật sự trôi nổi, không do systemd quản lý |
| Kill/dọn báo "Không đủ quyền" | Process/file thuộc root | Bấm "Thử với quyền quản trị" (Process Manager) hoặc chọn mục có nhãn "cần quyền root" (Cleaner) — hệ thống sẽ hỏi mật khẩu qua `pkexec` |
| Hộp thoại pkexec không hiện | Thiếu polkit authentication agent đang chạy (hiếm gặp trên Ubuntu Desktop chuẩn) | Đảm bảo đang chạy trong phiên desktop GNOME bình thường, không phải qua SSH/TTY thuần |
| CPU% luôn hiện 0% ở lần đầu | Bình thường — psutil cần 1 chu kỳ để "làm nóng" phép đo | Sẽ đúng từ lần refresh thứ 2 |
| Trang Tối ưu hệ thống không thấy service nào | Máy bạn không có systemd user-service nào ở trạng thái "enabled" | Bình thường, không phải lỗi — nhiều máy chỉ dùng autostart app, không có user-service riêng |
| Bật lại 1 autostart app không thấy tác dụng ngay | Autostart chỉ áp dụng ở lần đăng nhập tiếp theo | Đăng xuất/đăng nhập lại (hoặc khởi động lại) để thấy hiệu lực; đây là hành vi đúng theo chuẩn XDG |

## 8. Đóng gói thành file `.deb` (cài bằng `dpkg -i` hoặc `apt install`)

```bash
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

Kết quả: file `mini-cleaner_1.0.0_all.deb` ở thư mục gốc project. Cài bằng:

```bash
# Cách khuyến nghị — apt tự tải dependency còn thiếu
sudo apt install ./mini-cleaner_1.0.0_all.deb

# Hoặc cách truyền thống — nếu thiếu dependency sẽ cần chạy thêm lệnh 2
sudo dpkg -i mini-cleaner_1.0.0_all.deb
sudo apt --fix-broken install
```

Sau khi cài, chạy bằng lệnh `mini-cleaner` từ bất kỳ đâu, hoặc tìm "Mini Cleaner" trong menu ứng dụng.

**✅ Đã test cài đặt thật** (không chỉ lý thuyết) trên Ubuntu 24.04.4 LTS: `apt install ./mini-cleaner_...deb` tự động resolve và cài đúng `gir1.2-gtk-4.0 4.14.5`, `libadwaita-1-0 1.5.0`, `gir1.2-adw-1 1.5.0`, `python3-psutil 5.9.8`, `policykit-1` — không lỗi. Toàn bộ 5 module UI import thành công với GTK/Adwaita thật, và app khởi động hiển thị đúng giao diện khi chạy thử qua Xvfb (màn hình ảo).

### Tương thích qua các phiên bản Ubuntu

| Ubuntu | GTK4 | Libadwaita | Trạng thái |
|---|---|---|---|
| 22.04 LTS | 4.6 | 1.1 | ✅ Tương thích — code dùng `Gtk.Paned`, không phụ thuộc API chỉ có ở Libadwaita 1.4+ |
| 24.04 LTS | 4.14 | 1.5 | ✅ **Đã test cài + chạy thật**, xác nhận hoạt động đúng |
| 26.04 LTS ("Resolute Raccoon") | mới hơn | mới hơn | ✅ Nên chạy được — cùng bộ dependency (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `python3-psutil`) đều là gói ổn định, có mặt xuyên suốt các phiên bản. **Lưu ý riêng:** GNOME 50 trên Ubuntu 26.04 bỏ hẳn phiên đăng nhập X11, chỉ còn Wayland — tính năng "phát hiện process không cửa sổ" (dùng `wmctrl`, chỉ hoạt động trên X11) sẽ tự tắt trên Wayland để tránh báo sai, thay vì lỗi/crash (đã xử lý trong `core/process_utils.py`) |

Gói khai báo `Architecture: all` (Python thuần, không có mã biên dịch riêng CPU) nên cùng 1 file `.deb` chạy được trên cả amd64 và arm64, miễn hệ thống có đủ các gói phụ thuộc trên.

## 9. Bước tiếp theo (sau MVP 4 giai đoạn)

Roadmap ban đầu (4 giai đoạn) đã hoàn thành, và giờ đã có thể đóng gói `.deb`. Các hướng mở rộng tiếp theo nếu muốn:

- **Flatpak** — để phân phối qua Flathub, sandbox tốt hơn deb truyền thống
- **Lưu lịch sử** các lần dọn dẹp / tắt process để người dùng xem lại
- **Lên lịch dọn dẹp tự động** định kỳ (ví dụ mỗi tuần) qua systemd timer
- **Icon riêng** cho app thay vì dùng icon hệ thống chung
- **PPA riêng** trên Launchpad để người dùng cài qua `apt` mà không cần tải file `.deb` thủ công

Xem file kế hoạch tổng thể (`ke-hoach-mini-app-clean-optimize.md`) để đối chiếu roadmap gốc.
