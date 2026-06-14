import argparse
import queue

import desktop_client.main as desktop_main
from pynput import keyboard


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


def test_calculate_overlay_position_prefers_below_and_right_of_cursor():
    assert desktop_main.calculate_overlay_position(
        cursor_x=100,
        cursor_y=100,
        screen_width=1200,
        screen_height=900,
        overlay_width=300,
        overlay_height=200,
        padding=16,
    ) == (116, 116)


def test_calculate_overlay_position_flips_away_from_screen_edges():
    assert desktop_main.calculate_overlay_position(
        cursor_x=1150,
        cursor_y=850,
        screen_width=1200,
        screen_height=900,
        overlay_width=300,
        overlay_height=200,
        padding=16,
    ) == (834, 634)


def test_parse_trigger_key_supports_special_key_aliases():
    assert desktop_main.parse_trigger_key("right_shift") == keyboard.Key.shift_r
    assert desktop_main.parse_trigger_key("shift_r") == keyboard.Key.shift_r
    assert desktop_main.parse_trigger_key("space") == keyboard.Key.space


def test_parse_trigger_key_supports_single_character_keys():
    assert desktop_main.parse_trigger_key("x") == keyboard.KeyCode.from_char("x")


def test_double_press_detector_triggers_on_two_fast_trigger_key_presses():
    times = iter([10.0, 10.2])
    detector = desktop_main.DoublePressDetector(
        trigger_key=keyboard.Key.shift_r,
        window_seconds=0.35,
        clock=lambda: next(times),
    )

    assert detector.on_press(keyboard.Key.shift_r) is False
    assert detector.on_press(keyboard.Key.shift_r) is True


def test_double_press_detector_ignores_slow_trigger_key_presses():
    times = iter([10.0, 10.5])
    detector = desktop_main.DoublePressDetector(
        trigger_key=keyboard.Key.shift_r,
        window_seconds=0.35,
        clock=lambda: next(times),
    )

    assert detector.on_press(keyboard.Key.shift_r) is False
    assert detector.on_press(keyboard.Key.shift_r) is False


def test_double_press_detector_resets_on_non_trigger_key():
    times = iter([10.0, 10.1, 10.2])
    detector = desktop_main.DoublePressDetector(
        trigger_key=keyboard.Key.shift_r,
        window_seconds=0.35,
        clock=lambda: next(times),
    )

    assert detector.on_press(keyboard.Key.shift_r) is False
    assert detector.on_press(keyboard.Key.enter) is False
    assert detector.on_press(keyboard.Key.shift_r) is False


def test_resolve_desktop_settings_uses_env_settings_when_cli_values_are_missing():
    settings = desktop_main.DesktopSettings(
        backend_url="http://localhost:9000",
        trigger_key="alt_r",
        double_press_window=0.4,
        copy_delay=0.3,
        copy_timeout=3.0,
        mode="summary",
    )
    args = argparse.Namespace(
        backend_url=None,
        trigger_key=None,
        double_press_window=None,
        copy_delay=None,
        copy_timeout=None,
        mode=None,
    )

    resolved = desktop_main.resolve_desktop_settings(args, settings)

    assert resolved == settings


def test_resolve_desktop_settings_lets_cli_values_override_env_settings():
    settings = desktop_main.DesktopSettings(
        backend_url="http://localhost:9000",
        trigger_key="alt_r",
        double_press_window=0.4,
        copy_delay=0.3,
        copy_timeout=3.0,
        mode="summary",
    )
    args = argparse.Namespace(
        backend_url=None,
        trigger_key="shift_l",
        double_press_window=0.2,
        copy_delay=None,
        copy_timeout=None,
        mode="technical",
    )

    resolved = desktop_main.resolve_desktop_settings(args, settings)

    assert resolved.backend_url == "http://localhost:9000"
    assert resolved.trigger_key == "shift_l"
    assert resolved.double_press_window == 0.2
    assert resolved.copy_delay == 0.3
    assert resolved.copy_timeout == 3.0
    assert resolved.mode == "technical"


def test_handle_trigger_shows_loading_state_immediately(monkeypatch):
    popup_queue = queue.Queue()
    client = desktop_main.DesktopClient(
        backend_url="http://localhost:8000",
        mode="simple",
        popup_queue=popup_queue,
    )
    started = []

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            started.append((self.target, self.daemon))

    monkeypatch.setattr(desktop_main.threading, "Thread", FakeThread)

    client.handle_trigger()

    assert popup_queue.get_nowait() == (
        desktop_main.OVERLAY_TITLE,
        desktop_main.LOADING_MESSAGE,
    )
    assert started == [(client._explain_selection, True)]


def test_poll_popups_closes_overlays_from_queue():
    popup_queue = queue.Queue()
    popup_queue.put((desktop_main.CLOSE_OVERLAYS_EVENT, ""))
    closed = []

    class FakeRoot:
        def after(self, *args):
            pass

    class FakePopupManager:
        root = FakeRoot()

        def show(self, title, body):
            raise AssertionError("close events should not be shown")

        def close_all(self):
            closed.append(True)

    desktop_main.poll_popups(FakePopupManager(), popup_queue)

    assert closed == [True]


def test_popup_manager_reports_visible_overlay(monkeypatch):
    manager = desktop_main.PopupManager(root=object())

    class FakePopup:
        def __init__(self, exists=True, state="normal"):
            self.exists = exists
            self._state = state

        def winfo_exists(self):
            return self.exists

        def state(self):
            return self._state

    manager._popups["visible"] = (FakePopup(), object())

    assert manager.has_visible_overlay() is True

    manager._popups["visible"] = (FakePopup(state="withdrawn"), object())

    assert manager.has_visible_overlay() is False


def test_should_suppress_escape_event_only_when_overlay_is_visible():
    assert desktop_main.should_suppress_escape_event(
        event_type=10,
        key_code=desktop_main.MAC_ESCAPE_KEY_CODE,
        key_down_event_type=10,
        has_visible_overlay=True,
    ) is True
    assert desktop_main.should_suppress_escape_event(
        event_type=10,
        key_code=desktop_main.MAC_ESCAPE_KEY_CODE,
        key_down_event_type=10,
        has_visible_overlay=False,
    ) is False
    assert desktop_main.should_suppress_escape_event(
        event_type=10,
        key_code=1,
        key_down_event_type=10,
        has_visible_overlay=True,
    ) is False
