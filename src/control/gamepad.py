from __future__ import annotations
from .inputs import InputSource

#: gamepad button index -> action; analog sticks drive XY continuously.
DEFAULT_PAD_MAP = {
    "buttons": {0: "mount_toggle", 1: "home", 2: "zero_z",
                4: "step_down", 5: "step_up", 7: "quit"},
    "hat_to_z": True,                 # d-pad up/down -> z+/z-
    "deadzone": 0.35,
}


class GamepadInput(InputSource):
    """Gamepad jog backend built on `pygame` (optional dependency).

    Left stick jogs X/Y continuously, speed set by how far off center it's
    deflected; d-pad jogs Z continuously at full speed while held; face
    buttons toggle mount / home / zero / change step. Everything stops the
    instant the stick returns to center or the d-pad releases. Reference
    implementation -- tune the map to your controller.
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
        prev_hy = 0

        while session.running:
            pygame.event.pump()
            for event in pygame.event.get():
                if event.type == pygame.JOYBUTTONDOWN:
                    action = self.map["buttons"].get(event.button)
                    if action:
                        session.handle(action)

            # left stick -> continuous X/Y, speed scaled by deflection
            x, y = pad.get_axis(0), pad.get_axis(1)
            if abs(x) > dead:
                session.press("x+" if x > 0 else "x-", speed=abs(x))
                session.release("x-" if x > 0 else "x+")
            else:
                session.release("x+")
                session.release("x-")
            if abs(y) > dead:
                session.press("y-" if y > 0 else "y+", speed=abs(y))   # up is -y on sticks
                session.release("y+" if y > 0 else "y-")
            else:
                session.release("y+")
                session.release("y-")

            # d-pad -> continuous Z at full speed while held
            if self.map.get("hat_to_z") and pad.get_numhats():
                _, hy = pad.get_hat(0)
                if hy != prev_hy:
                    if prev_hy > 0:
                        session.release("z+")
                    elif prev_hy < 0:
                        session.release("z-")
                    if hy > 0:
                        session.press("z+")
                    elif hy < 0:
                        session.press("z-")
                    prev_hy = hy
            time.sleep(self.dt)

        session.c.end_jog()   # safety: make sure nothing is left moving
        pygame.quit()
