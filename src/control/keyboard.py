from __future__ import annotations
from .inputs import InputSource

#: key character -> action name. Arrow keys map via pynput Key names below.
DEFAULT_KEYMAP = {
    "a": "x-", "d": "x+", "w": "y+", "s": "y-",
    "q": "z+", "e": "z-", "r": "plunger+", "f": "plunger-",
    "+": "step_up", "-": "step_down", "m": "mount_toggle",
    "h": "home", "\x1b": "quit",  # Esc
}


class KeyboardInput(InputSource):
    """Keyboard jog backend built on `pynput` (optional dependency).

    Reference implementation: install pynput to use it. It listens globally,
    so it also works over SSH forwarding / headless setups where a terminal
    raw-mode reader would not.
    """

    def __init__(self, keymap: dict | None = None):
        self.keymap = keymap or DEFAULT_KEYMAP

    def run(self, session) -> None:
        from pynput import keyboard  # lazy import

        def on_press(key):
            try:
                name = key.char
            except AttributeError:
                name = f"<{key.name}>"          # e.g. <up>, <down>
            action = self.keymap.get(name)
            if action:
                session.handle(action)
            if not session.running:
                return False                    # stop the listener

        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()
