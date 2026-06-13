import argparse
import platform
import queue
import threading
import time
import tkinter as tk
import uuid
from tkinter import ttk

import httpx
import pyautogui
import pyperclip
from pynput import keyboard

DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_HOTKEY = "<ctrl>+<shift>+e"
DEFAULT_COPY_DELAY_SECONDS = 0.25
DEFAULT_COPY_TIMEOUT_SECONDS = 2.0
NO_SELECTION_COOLDOWN_SECONDS = 2.0
NO_SELECTION_MESSAGE = (
    "No selected text could be copied.\n\n"
    "Try releasing the hotkey immediately after pressing it. On macOS, make sure "
    "Accessibility permission is enabled for the app that launched this client "
    "(Terminal, iTerm, or VS Code), then restart the desktop client."
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


def request_explanation(backend_url: str, text: str, mode: str) -> str:
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{backend_url.rstrip('/')}/api/explain",
            json={"text": text, "mode": mode},
        )
        response.raise_for_status()
        return response.json()["answer"]


class PopupManager:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
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
                popup.deiconify()
                popup.lift()
                popup.focus_force()
                return

        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.geometry("620x420")
        popup.attributes("-topmost", True)

        frame = ttk.Frame(popup, padding=12)
        frame.pack(fill="both", expand=True)

        text = tk.Text(frame, wrap="word", font=("Arial", 13), padx=8, pady=8)
        text.insert("1.0", body)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

        def close_popup() -> None:
            self._popups.pop(title, None)
            popup.destroy()

        popup.protocol("WM_DELETE_WINDOW", close_popup)
        close = ttk.Button(frame, text="Close", command=close_popup)
        close.pack(anchor="e", pady=(10, 0))
        self._popups[title] = (popup, text)


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

    def handle_hotkey(self) -> None:
        if not self._lock.acquire(blocking=False):
            return

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
                    self.popup_queue.put(("AI Reading Assistant", NO_SELECTION_MESSAGE))
                    self._last_no_selection_at = now
                return

            answer = request_explanation(
                backend_url=self.backend_url,
                text=selected_text,
                mode=self.mode,
            )
            self.popup_queue.put(("AI Explanation", answer))
        except Exception as exc:
            self.popup_queue.put(("AI Reading Assistant Error", str(exc)))
        finally:
            self._lock.release()


def poll_popups(
    popup_manager: PopupManager,
    popup_queue: queue.Queue[tuple[str, str]],
    interval_ms: int = 100,
) -> None:
    while True:
        try:
            title, body = popup_queue.get_nowait()
        except queue.Empty:
            break

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
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--hotkey", default=DEFAULT_HOTKEY)
    parser.add_argument(
        "--copy-delay",
        type=float,
        default=DEFAULT_COPY_DELAY_SECONDS,
        help=(
            "Seconds to wait after the global hotkey fires before sending copy. "
            "Increase this if the selected text is not copied."
        ),
    )
    parser.add_argument(
        "--copy-timeout",
        type=float,
        default=DEFAULT_COPY_TIMEOUT_SECONDS,
        help="Seconds to wait for the clipboard to update after sending copy.",
    )
    parser.add_argument(
        "--mode",
        default="simple",
        choices=("simple", "summary", "technical", "example"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    popup_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    client = DesktopClient(
        backend_url=args.backend_url,
        mode=args.mode,
        popup_queue=popup_queue,
        copy_timeout_seconds=args.copy_timeout,
        copy_delay_seconds=args.copy_delay,
    )

    root = tk.Tk()
    root.withdraw()
    popup_manager = PopupManager(root)
    root.after(100, poll_popups, popup_manager, popup_queue)

    print(f"AI Reading Assistant running. Select text and press {args.hotkey}.")
    listener = keyboard.GlobalHotKeys({args.hotkey: client.handle_hotkey})
    listener.start()

    try:
        root.mainloop()
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
