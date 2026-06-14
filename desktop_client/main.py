import argparse
import platform
import queue
import threading
import time
import tkinter as tk
import uuid
from typing import Literal
from tkinter import ttk

import httpx
import pyautogui
import pyperclip
from pydantic_settings import BaseSettings, SettingsConfigDict
from pynput import keyboard

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_TRIGGER_KEY = "shift_r"
DEFAULT_DOUBLE_PRESS_WINDOW_SECONDS = 0.35
DEFAULT_COPY_DELAY_SECONDS = 0.25
DEFAULT_COPY_TIMEOUT_SECONDS = 2.0
DEFAULT_OVERLAY_WIDTH = 620
DEFAULT_OVERLAY_HEIGHT = 300
DEFAULT_OVERLAY_PADDING = 16
DEFAULT_POPUP_POLL_INTERVAL_MS = 25
NO_SELECTION_COOLDOWN_SECONDS = 2.0
Mode = Literal["simple", "summary", "technical", "example"]
OVERLAY_TITLE = "AI Reading Assistant"
LOADING_MESSAGE = "Reading selected text..."
CLOSE_OVERLAYS_EVENT = "__AI_READING_ASSISTANT_CLOSE_OVERLAYS__"
MAC_ESCAPE_KEY_CODE = 53
NO_SELECTION_MESSAGE = (
    "No selected text could be copied.\n\n"
    "Try pressing the trigger key twice without holding it down. On macOS, make sure "
    "Accessibility permission is enabled for the app that launched this client "
    "(Terminal, iTerm, or VS Code), then restart the desktop client."
)


class DesktopSettings(BaseSettings):
    backend_url: str = DEFAULT_BACKEND_URL
    trigger_key: str = DEFAULT_TRIGGER_KEY
    double_press_window: float = DEFAULT_DOUBLE_PRESS_WINDOW_SECONDS
    copy_delay: float = DEFAULT_COPY_DELAY_SECONDS
    copy_timeout: float = DEFAULT_COPY_TIMEOUT_SECONDS
    mode: Mode = "simple"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DESKTOP_",
        extra="ignore",
    )


def copy_selected_text(
    timeout_seconds: float = DEFAULT_COPY_TIMEOUT_SECONDS,
    delay_seconds: float = DEFAULT_COPY_DELAY_SECONDS,
) -> str:
    previous_clipboard = pyperclip.paste()
    clipboard_marker = f"__AI_READING_ASSISTANT_COPY_MARKER_{uuid.uuid4()}__"
    pyperclip.copy(clipboard_marker)

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    if platform.system() == "Darwin":
        pyautogui.hotkey("command", "c")
    else:
        pyautogui.hotkey("ctrl", "c")

    deadline = time.monotonic() + timeout_seconds
    selected_text = ""
    while time.monotonic() < deadline:
        selected_text = pyperclip.paste()
        if selected_text != clipboard_marker:
            break
        time.sleep(0.05)

    if selected_text == clipboard_marker or not selected_text.strip():
        pyperclip.copy(previous_clipboard)
        return ""

    return selected_text.strip()


def calculate_overlay_position(
    cursor_x: int,
    cursor_y: int,
    screen_width: int,
    screen_height: int,
    overlay_width: int = DEFAULT_OVERLAY_WIDTH,
    overlay_height: int = DEFAULT_OVERLAY_HEIGHT,
    padding: int = DEFAULT_OVERLAY_PADDING,
) -> tuple[int, int]:
    x = cursor_x + padding
    y = cursor_y + padding

    if x + overlay_width + padding > screen_width:
        x = cursor_x - overlay_width - padding
    if y + overlay_height + padding > screen_height:
        y = cursor_y - overlay_height - padding

    x = max(padding, min(x, screen_width - overlay_width - padding))
    y = max(padding, min(y, screen_height - overlay_height - padding))
    return x, y


def request_explanation(backend_url: str, text: str, mode: str) -> str:
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{backend_url.rstrip('/')}/api/explain",
            json={"text": text, "mode": mode},
        )
        response.raise_for_status()
        return response.json()["answer"]


def parse_trigger_key(name: str) -> keyboard.Key | keyboard.KeyCode:
    normalized = name.strip().lower()
    aliases = {
        "right_shift": "shift_r",
        "left_shift": "shift_l",
        "right_cmd": "cmd_r",
        "left_cmd": "cmd_l",
        "right_alt": "alt_r",
        "left_alt": "alt_l",
        "option_r": "alt_r",
        "option_l": "alt_l",
        "return": "enter",
    }
    normalized = aliases.get(normalized, normalized)

    special_key = getattr(keyboard.Key, normalized, None)
    if special_key is not None:
        return special_key

    if len(normalized) == 1:
        return keyboard.KeyCode.from_char(normalized)

    raise ValueError(f"Unsupported trigger key: {name}")


def should_suppress_escape_event(
    event_type: int,
    key_code: int,
    key_down_event_type: int,
    has_visible_overlay: bool,
) -> bool:
    return (
        has_visible_overlay
        and event_type == key_down_event_type
        and key_code == MAC_ESCAPE_KEY_CODE
    )


class DoublePressDetector:
    def __init__(
        self,
        trigger_key: keyboard.Key | keyboard.KeyCode,
        window_seconds: float = DEFAULT_DOUBLE_PRESS_WINDOW_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self.trigger_key = trigger_key
        self.window_seconds = window_seconds
        self.clock = clock
        self._last_press_at: float | None = None

    def on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> bool:
        now = self.clock()
        if key != self.trigger_key:
            self._last_press_at = None
            return False

        if (
            self._last_press_at is not None
            and now - self._last_press_at <= self.window_seconds
        ):
            self._last_press_at = None
            return True

        self._last_press_at = now
        return False


class PopupManager:
    def __init__(
        self,
        root: tk.Tk,
        overlay_width: int = DEFAULT_OVERLAY_WIDTH,
        overlay_height: int = DEFAULT_OVERLAY_HEIGHT,
    ) -> None:
        self.root = root
        self.overlay_width = overlay_width
        self.overlay_height = overlay_height
        self._popups: dict[str, tuple[tk.Toplevel, tk.Text]] = {}

    def show(self, title: str, body: str) -> None:
        existing = self._popups.get(title)
        if existing is not None:
            popup, text = existing
            if popup.winfo_exists():
                text.configure(state="normal")
                text.delete("1.0", "end")
                text.insert("1.0", body)
                text.configure(state="disabled")
                self._position_overlay(popup)
                popup.deiconify()
                popup.lift()
                return

        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.resizable(False, False)

        frame = ttk.Frame(popup, padding=10, relief="solid", borderwidth=1)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 8))

        label = ttk.Label(header, text=title, font=("Arial", 13, "bold"))
        label.pack(side="left")

        def close_popup() -> None:
            self._popups.pop(title, None)
            popup.destroy()

        close = ttk.Button(header, text="x", width=3, command=close_popup)
        close.pack(side="right")

        text = tk.Text(
            frame,
            wrap="word",
            font=("Arial", 13),
            padx=8,
            pady=8,
            relief="flat",
            borderwidth=0,
        )
        text.insert("1.0", body)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

        self._position_overlay(popup)
        self._popups[title] = (popup, text)

    def close_all(self) -> None:
        for title, (popup, _) in list(self._popups.items()):
            if popup.winfo_exists():
                popup.destroy()
            self._popups.pop(title, None)

    def has_visible_overlay(self) -> bool:
        return any(
            popup.winfo_exists() and popup.state() != "withdrawn"
            for popup, _ in self._popups.values()
        )

    def _position_overlay(self, popup: tk.Toplevel) -> None:
        try:
            cursor_x, cursor_y = pyautogui.position()
        except Exception:
            cursor_x, cursor_y = self.root.winfo_pointerxy()

        x, y = calculate_overlay_position(
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            screen_width=self.root.winfo_screenwidth(),
            screen_height=self.root.winfo_screenheight(),
            overlay_width=self.overlay_width,
            overlay_height=self.overlay_height,
        )
        popup.geometry(f"{self.overlay_width}x{self.overlay_height}+{x}+{y}")


class MacOverlayManager:
    def __init__(
        self,
        root: tk.Tk,
        overlay_width: int = DEFAULT_OVERLAY_WIDTH,
        overlay_height: int = DEFAULT_OVERLAY_HEIGHT,
    ) -> None:
        import AppKit

        self.AppKit = AppKit
        self.root = root
        self.overlay_width = overlay_width
        self.overlay_height = overlay_height
        self._popups: dict[str, dict[str, object]] = {}

        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def show(self, title: str, body: str) -> None:
        existing = self._popups.get(title)
        if existing is None:
            existing = self._create_panel(title)
            self._popups[title] = existing
        else:
            existing["title_label"].setStringValue_(title)

        panel = existing["panel"]
        text_view = existing["text_view"]
        spinner = existing["spinner"]

        if body == LOADING_MESSAGE:
            spinner.setHidden_(False)
            spinner.startAnimation_(None)
        else:
            spinner.stopAnimation_(None)
            spinner.setHidden_(True)

        text_view.setString_(body)
        self._position_overlay(panel)
        panel.orderFrontRegardless()

    def close_all(self) -> None:
        for popup in self._popups.values():
            popup["panel"].orderOut_(None)

    def has_visible_overlay(self) -> bool:
        return any(popup["panel"].isVisible() for popup in self._popups.values())

    def _create_panel(self, title: str) -> dict[str, object]:
        AppKit = self.AppKit
        import objc

        class CloseButtonTarget(AppKit.NSObject):
            panel = objc.ivar()

            def initWithPanel_(self, panel):
                self = objc.super(CloseButtonTarget, self).init()
                if self is None:
                    return None

                self.panel = panel
                return self

            def closeOverlay_(self, sender) -> None:
                self.panel.orderOut_(None)

        frame = AppKit.NSMakeRect(0, 0, self.overlay_width, self.overlay_height)
        style_mask = AppKit.NSWindowStyleMaskNonactivatingPanel
        panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style_mask,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        panel.setTitle_(title)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setLevel_(AppKit.NSFloatingWindowLevel)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setWorksWhenModal_(True)
        panel.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
            | AppKit.NSWindowCollectionBehaviorTransient
        )

        content_view = panel.contentView()
        content_frame = content_view.bounds()
        content_view.setWantsLayer_(True)

        material_view = AppKit.NSVisualEffectView.alloc().initWithFrame_(content_frame)
        material_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        material_view.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        material_view.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
        material_view.setState_(AppKit.NSVisualEffectStateActive)
        material_view.setWantsLayer_(True)
        material_layer = material_view.layer()
        material_layer.setCornerRadius_(14)
        material_layer.setMasksToBounds_(True)
        content_view.addSubview_(material_view)

        header_height = 46
        margin = 16
        button_size = 24

        title_label = AppKit.NSTextField.labelWithString_(title)
        title_label.setFrame_(
            AppKit.NSMakeRect(
                margin,
                self.overlay_height - header_height + 12,
                self.overlay_width - (margin * 2) - button_size,
                22,
            )
        )
        title_label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(13))
        title_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        title_label.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
        material_view.addSubview_(title_label)

        close_target = CloseButtonTarget.alloc().initWithPanel_(panel)
        close_button = AppKit.NSButton.buttonWithTitle_target_action_(
            "x",
            close_target,
            "closeOverlay:",
        )
        close_button.setFrame_(
            AppKit.NSMakeRect(
                self.overlay_width - margin - 28,
                self.overlay_height - header_height + 8,
                28,
                28,
            )
        )
        close_button.setBordered_(False)
        close_button.setFont_(AppKit.NSFont.boldSystemFontOfSize_(15))
        close_button.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
        close_button.setWantsLayer_(True)
        close_button.layer().setCornerRadius_(14)
        close_button.layer().setMasksToBounds_(True)
        close_button.setAutoresizingMask_(
            AppKit.NSViewMinXMargin | AppKit.NSViewMinYMargin
        )
        material_view.addSubview_(close_button)

        def set_close_hovered(is_hovered: bool) -> None:
            if is_hovered:
                close_button.setContentTintColor_(AppKit.NSColor.systemRedColor())
                close_button.layer().setBackgroundColor_(
                    AppKit.NSColor.systemRedColor().colorWithAlphaComponent_(0.16).CGColor()
                )
            else:
                close_button.setContentTintColor_(AppKit.NSColor.secondaryLabelColor())
                close_button.layer().setBackgroundColor_(AppKit.NSColor.clearColor().CGColor())

        def close_click_monitor(event):
            if event.window() == panel and AppKit.NSPointInRect(
                event.locationInWindow(),
                close_button.frame(),
            ):
                panel.orderOut_(None)
                return None

            return event

        def close_hover_monitor(event):
            if event.window() == panel:
                set_close_hovered(
                    AppKit.NSPointInRect(event.locationInWindow(), close_button.frame())
                )
            else:
                set_close_hovered(False)

            return event

        panel.setAcceptsMouseMovedEvents_(True)
        close_click_monitor_token = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskLeftMouseDown,
            close_click_monitor,
        )
        close_hover_monitor_token = AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            AppKit.NSEventMaskMouseMoved,
            close_hover_monitor,
        )

        spinner = AppKit.NSProgressIndicator.alloc().initWithFrame_(
            AppKit.NSMakeRect(margin, self.overlay_height - header_height - 24, 18, 18)
        )
        spinner.setStyle_(AppKit.NSProgressIndicatorStyleSpinning)
        spinner.setControlSize_(AppKit.NSControlSizeSmall)
        spinner.setDisplayedWhenStopped_(False)
        spinner.setHidden_(True)
        spinner.setAutoresizingMask_(AppKit.NSViewMaxXMargin | AppKit.NSViewMinYMargin)
        material_view.addSubview_(spinner)

        scroll_frame = AppKit.NSMakeRect(
            margin,
            margin,
            self.overlay_width - (margin * 2),
            self.overlay_height - header_height - margin,
        )
        scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(scroll_frame)
        scroll_view.setAutoresizingMask_(
            AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable
        )
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setBorderType_(AppKit.NSNoBorder)
        scroll_view.setDrawsBackground_(False)

        text_view = AppKit.NSTextView.alloc().initWithFrame_(scroll_frame)
        text_view.setEditable_(False)
        text_view.setSelectable_(True)
        text_view.setFont_(AppKit.NSFont.systemFontOfSize_(15))
        text_view.setTextColor_(AppKit.NSColor.labelColor())
        text_view.setDrawsBackground_(False)
        text_view.setTextContainerInset_(AppKit.NSMakeSize(0, 8))
        text_view.setVerticallyResizable_(True)
        text_view.setHorizontallyResizable_(False)
        text_view.textContainer().setWidthTracksTextView_(True)
        scroll_view.setDocumentView_(text_view)
        material_view.addSubview_(scroll_view)

        return {
            "panel": panel,
            "text_view": text_view,
            "title_label": title_label,
            "spinner": spinner,
            "close_target": close_target,
            "close_click_monitor": close_click_monitor_token,
            "close_hover_monitor": close_hover_monitor_token,
        }

    def _position_overlay(self, panel: object) -> None:
        AppKit = self.AppKit
        try:
            cursor_x, cursor_y = pyautogui.position()
        except Exception:
            cursor_x, cursor_y = self.root.winfo_pointerxy()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x, top_y = calculate_overlay_position(
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            screen_width=screen_width,
            screen_height=screen_height,
            overlay_width=self.overlay_width,
            overlay_height=self.overlay_height,
        )
        bottom_y = screen_height - top_y - self.overlay_height
        panel.setFrame_display_(
            AppKit.NSMakeRect(x, bottom_y, self.overlay_width, self.overlay_height),
            True,
        )


def create_popup_manager(root: tk.Tk) -> PopupManager | MacOverlayManager:
    if platform.system() == "Darwin":
        try:
            return MacOverlayManager(root)
        except Exception as exc:
            print(f"Native macOS overlay unavailable; falling back to Tk overlay: {exc}")

    return PopupManager(root)


class DesktopClient:
    def __init__(
        self,
        backend_url: str,
        mode: str,
        popup_queue: queue.Queue[tuple[str, str]],
        copy_timeout_seconds: float = DEFAULT_COPY_TIMEOUT_SECONDS,
        copy_delay_seconds: float = DEFAULT_COPY_DELAY_SECONDS,
    ) -> None:
        self.backend_url = backend_url
        self.mode = mode
        self.popup_queue = popup_queue
        self.copy_timeout_seconds = copy_timeout_seconds
        self.copy_delay_seconds = copy_delay_seconds
        self._lock = threading.Lock()
        self._last_no_selection_at = 0.0

    def handle_trigger(self) -> None:
        if not self._lock.acquire(blocking=False):
            return

        self.popup_queue.put((OVERLAY_TITLE, LOADING_MESSAGE))
        thread = threading.Thread(target=self._explain_selection, daemon=True)
        thread.start()

    def _explain_selection(self) -> None:
        try:
            selected_text = copy_selected_text(
                timeout_seconds=self.copy_timeout_seconds,
                delay_seconds=self.copy_delay_seconds,
            )
            if not selected_text:
                now = time.monotonic()
                if now - self._last_no_selection_at >= NO_SELECTION_COOLDOWN_SECONDS:
                    self.popup_queue.put((OVERLAY_TITLE, NO_SELECTION_MESSAGE))
                    self._last_no_selection_at = now
                return

            answer = request_explanation(
                backend_url=self.backend_url,
                text=selected_text,
                mode=self.mode,
            )
            self.popup_queue.put((OVERLAY_TITLE, answer))
        except Exception as exc:
            self.popup_queue.put((OVERLAY_TITLE, f"Something went wrong:\n\n{exc}"))
        finally:
            self._lock.release()


def poll_popups(
    popup_manager: PopupManager,
    popup_queue: queue.Queue[tuple[str, str]],
    interval_ms: int = DEFAULT_POPUP_POLL_INTERVAL_MS,
) -> None:
    while True:
        try:
            title, body = popup_queue.get_nowait()
        except queue.Empty:
            break

        if title == CLOSE_OVERLAYS_EVENT:
            popup_manager.close_all()
            continue

        popup_manager.show(title, body)

    popup_manager.root.after(
        interval_ms,
        poll_popups,
        popup_manager,
        popup_queue,
        interval_ms,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Reading Assistant desktop client")
    parser.add_argument("--backend-url")
    parser.add_argument(
        "--trigger-key",
        help=(
            "Key to double-press for triggering the assistant. Defaults to shift_r "
            "because Space scrolls many PDF readers."
        ),
    )
    parser.add_argument(
        "--double-press-window",
        "--double-space-window",
        dest="double_press_window",
        type=float,
        help="Maximum seconds between two trigger-key presses.",
    )
    parser.add_argument(
        "--copy-delay",
        type=float,
        help=(
            "Seconds to wait after the double-press trigger fires before sending copy. "
            "Increase this if the selected text is not copied."
        ),
    )
    parser.add_argument(
        "--copy-timeout",
        type=float,
        help="Seconds to wait for the clipboard to update after sending copy.",
    )
    parser.add_argument(
        "--mode",
        choices=("simple", "summary", "technical", "example"),
    )
    return parser.parse_args()


def resolve_desktop_settings(
    args: argparse.Namespace,
    settings: DesktopSettings | None = None,
) -> DesktopSettings:
    settings = settings or DesktopSettings()
    overrides = {
        key: value
        for key, value in vars(args).items()
        if value is not None
    }
    if not overrides:
        return settings

    return settings.model_copy(update=overrides)


def main() -> None:
    args = parse_args()
    settings = resolve_desktop_settings(args)
    popup_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    client = DesktopClient(
        backend_url=settings.backend_url,
        mode=settings.mode,
        popup_queue=popup_queue,
        copy_timeout_seconds=settings.copy_timeout,
        copy_delay_seconds=settings.copy_delay,
    )

    root = tk.Tk()
    root.withdraw()
    popup_manager = create_popup_manager(root)
    root.after(DEFAULT_POPUP_POLL_INTERVAL_MS, poll_popups, popup_manager, popup_queue)

    trigger_key = parse_trigger_key(settings.trigger_key)
    detector = DoublePressDetector(
        trigger_key=trigger_key,
        window_seconds=settings.double_press_window,
    )

    def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if detector.on_press(key):
            client.handle_trigger()

    listener_kwargs = {"on_press": on_press}
    if platform.system() == "Darwin":
        import Quartz

        def intercept(event_type, event):
            key_code = Quartz.CGEventGetIntegerValueField(
                event,
                Quartz.kCGKeyboardEventKeycode,
            )
            if should_suppress_escape_event(
                event_type=event_type,
                key_code=key_code,
                key_down_event_type=Quartz.kCGEventKeyDown,
                has_visible_overlay=popup_manager.has_visible_overlay(),
            ):
                popup_queue.put((CLOSE_OVERLAYS_EVENT, ""))
                return None

            return event

        listener_kwargs["intercept"] = intercept

    print(
        "AI Reading Assistant running. "
        f"Select text and press {settings.trigger_key} twice."
    )
    listener = keyboard.Listener(**listener_kwargs)
    listener.start()

    try:
        root.mainloop()
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
