from core import junk_scanner as js


def test_scan_hides_zero_size(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    full = tmp_path / "full"
    full.mkdir()
    (full / "f").write_bytes(b"x" * 100)

    def fake_defs():
        return [
            ("a", "A", str(empty), [str(empty)], None),
            ("b", "B", str(full), [str(full)], ["false"]),
        ]

    monkeypatch.setattr(js, "_iter_dev_tool_specs", fake_defs, raising=False)
    result = js.scan_dev_tool_caches()
    assert len(result) == 1
    assert result[0].id == "b"
    assert result[0].size_bytes >= 100


def test_clean_uses_cli_when_available(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "f").write_bytes(b"data")
    tool = js.DevToolCache("t", "T", str(d), [str(d)], 4, ["true"])
    ok, msg = js.clean_dev_tool_cache(tool)
    assert ok is True
    assert (d / "f").exists()
    assert "CLI" in msg


def test_clean_fallback_deletes_paths(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "f").write_bytes(b"data")
    tool = js.DevToolCache("t", "T", str(d), [str(d)], 4, ["false"])
    ok, msg = js.clean_dev_tool_cache(tool)
    assert ok is True
    assert not (d / "f").exists()


def test_clean_no_cli_deletes_paths(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "f").write_bytes(b"data")
    tool = js.DevToolCache("t", "T", str(d), [str(d)], 4, None)
    ok, msg = js.clean_dev_tool_cache(tool)
    assert ok is True
    assert not list(d.iterdir())


def test_clean_go_always_clears_scanned_paths(tmp_path, monkeypatch):
    mod = tmp_path / "mod"
    build = tmp_path / "go-build"
    mod.mkdir()
    build.mkdir()
    (mod / "pkg").write_bytes(b"module-cache")
    (build / "obj").write_bytes(b"build-cache")

    def fake_which(name):
        return None  # không gọi CLI; chỉ cần fallback xóa path đã quét

    monkeypatch.setattr("shutil.which", fake_which)
    tool = js.DevToolCache(
        "go", "Cache Go", "hint", [str(mod), str(build)], 20, ["go", "clean", "-modcache"]
    )
    ok, msg = js.clean_dev_tool_cache(tool)
    assert ok is True
    assert not (mod / "pkg").exists()
    assert not (build / "obj").exists()
