from __future__ import annotations
from .inputs import InputSource

#: gamepad button index -> action; analog sticks drive XY continuously.
DEFAULT_PAD_MAP = {
    "buttons": {0: "mount_toggle", 1: "home", 4: "step_down", 5: "step_up",
                7: "quit"},
    "hat_to_z": True,                 # d-pad up/down -> z+/z-
    "deadzone": 0.35,
}


class GamepadInput(InputSource):
    """Gamepad jog backend built on `pygame` (optional dependency).

    Left stick jogs X/Y, d-pad jogs Z, face buttons toggle mount / home /
    change step. Reference implementation -- tune the map to your controller.
    """

    def __init__(self, mapping: dict | None = None, poll_hz: float = 30.0):
        self.map = mapping or DEFAULT_PAD_MAP
        self.dt = 1.0 / poll_hz

    def run(self, session) -> None:
        import time
        import pygame  # lazy import

        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("no gamepad detected")
        pad = pygame.joystick.Joystick(0)
        pad.init()
        dead = self.map["deadzone"]

        while session.running:
            pygame.event.pump()
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    action = self.map["buttons"].get(event.button)
                    if action:
                        session.handle(action)
            # analog sticks -> XY nudges
            x, y = pad.get_axis(0), pad.get_axis(1)
            if abs(x) > dead:
                session.handle("x+" if x > 0 else "x-")
            if abs(y) > dead:
                session.handle("y-" if y > 0 else "y+")   # up is -y on sticks
            if self.map.get("hat_to_z") and pad.get_numhats():
                _, hy = pad.get_hat(0)
                if hy > 0:
                    session.handle("z+")
                elif hy < 0:
                    session.handle("z-")
            time.sleep(self.dt)

        pygame.quit()
