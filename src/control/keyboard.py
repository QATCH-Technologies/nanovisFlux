from __future__ import annotations
from .inputs import InputSource

#: key character -> action name. Arrow keys map via pynput Key names below.
DEFAULT_KEYMAP = {
    "a": "x-", "d": "x+", "w": "y+", "s": "y-",
    "q": "z+", "e": "z-", "r": "plunger+", "f": "plunger-",
    "+": "step_up", "-": "step_down", "m": "mount_toggle", "0": "zero_z",
    "h": "home", "\x1b": "quit",  # Esc
}


class KeyboardInput(InputSource):
    """Keyboard jog backend built on `pynput` (optional dependency).

    Movement keys drive a continuous move at the toggleable jog speed
    (step_up/step_down) for as long as they're held, and quick-stop the
    instant they're released. Reference implementation: install pynput to
    use it. It listens globally, so it also works over SSH forwarding /
    headless setups where a terminal raw-mode reader would not.
    """

    def __init__(self, keymap: dict | None = None):
        self.keymap = keymap or DEFAULT_KEYMAP

    def run(self, session) -> None:
        from pynput import keyboard  # lazy import

        def _name(key):
            try:
                return key.char
            except AttributeError:
                return f"<{key.name}>"          # e.g. <up>, <down>

        holder: list = []  # holds the listener so on_press can stop it -- avoids
                            # returning False, which pynput's stub disallows

        def on_press(key):
            action = self.keymap.get(_name(key))
            if action:
                session.press(action)
            if not session.running and holder:
                holder[0].stop()

        def on_release(key):
            action = self.keymap.get(_name(key))
            if action:
                session.release(action)

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        holder.append(listener)
        with listener:
            listener.join()
