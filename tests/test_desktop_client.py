import desktop_client.main as desktop_main


def test_copy_selected_text_waits_before_copy(monkeypatch):
    clipboard_values = ["original"]
    sleeps = []

    monkeypatch.setattr(desktop_main.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(desktop_main.time, "sleep", sleeps.append)
    monkeypatch.setattr(desktop_main.time, "monotonic", lambda: 0)
    monkeypatch.setattr(desktop_main.pyperclip, "paste", lambda: clipboard_values[-1])
    monkeypatch.setattr(desktop_main.pyperclip, "copy", clipboard_values.append)

    def fake_hotkey(*keys):
        assert keys == ("command", "c")
        clipboard_values.append("selected text")

    monkeypatch.setattr(desktop_main.pyautogui, "hotkey", fake_hotkey)

    assert desktop_main.copy_selected_text(delay_seconds=0.25) == "selected text"
    assert sleeps == [0.25]


def test_copy_selected_text_restores_clipboard_when_selection_missing(monkeypatch):
    clipboard_values = ["original"]
    monotonic_values = iter([0, 2])

    monkeypatch.setattr(desktop_main.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(desktop_main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(desktop_main.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(desktop_main.pyperclip, "paste", lambda: clipboard_values[-1])
    monkeypatch.setattr(desktop_main.pyperclip, "copy", clipboard_values.append)
    monkeypatch.setattr(desktop_main.pyautogui, "hotkey", lambda *keys: None)

    assert desktop_main.copy_selected_text(
        timeout_seconds=1.0,
        delay_seconds=0,
    ) == ""
    assert clipboard_values[-1] == "original"
