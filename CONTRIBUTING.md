# Contributing

## Setup

```bash
pip install -e ".[ml,test]"
```

or, for a flat all-in-one install matching what CI uses:

```bash
pip install -r requirements.txt
```

Python 3.11.7+ is required.

## Running tests

```bash
pytest                        # full suite
pytest tests/test_robot/      # one subpackage
pytest -k jog                 # by name
```

`tests/` mirrors `src/`'s package layout module-for-module
(`tests/test_<pkg>/test_<module>.py`) -- when adding a module under `src/`,
add its test alongside the matching subpackage.

The suite is built around `SimulatedTransport`, an in-memory G-code firmware
emulator (see `src/transport/simulated.py`), so it requires no real
instrument and runs identically on Windows and Linux. Motion-verification
tests (`Robot._await_settled`'s stall-detection/retry behavior, calibration
extrapolation guards, etc.) exercise real firmware *logic* -- probe contact,
G1 real-time move completion, homing, endstop clamping -- without touching
hardware. Tests that do need real serial I/O (`SerialTransport`) mock
`pyserial` directly rather than opening a port.

## Style

flake8 + pylint. flake8 is a hard merge gate for syntax errors and undefined
names only (`E9,F63,F7,F82`); everything else from flake8 and all of pylint
is informational (`--exit-zero`) -- pylint's default ruleset is too strict
to use as a hard gate here. pylint reads this repo's `.pylintrc`.

```bash
flake8 . --select=E9,F63,F7,F82          # the hard gate
flake8 . --exit-zero --max-line-length=127
pylint --exit-zero $(git ls-files '*.py')
```

## CI

Four workflows run under `.github/workflows/`:

- **test.yml** -- the full `pytest` suite on Python 3.11, matrixed across
  `windows-latest` and `ubuntu-latest` (this is real hardware-control code
  with Windows-specific serial/path assumptions in places -- the Windows
  leg is what actually verifies cross-platform behavior, not just code
  review). Uploads a coverage XML artifact from the Ubuntu/3.11 leg.
- **style.yml** -- the flake8 + pylint gate described above.
- **build.yml** -- builds the sdist/wheel and installs it into a clean venv,
  then imports the built package and resolves `Robot`/`AxisId`/etc. from it,
  to catch packaging regressions (a new module `find_packages()` doesn't
  pick up, a missing data file) that passing tests alone wouldn't catch,
  since tests run against the working tree, not a built wheel.
- **codeql.yml** -- weekly + on-push/PR security scan across both the
  Python source and the GitHub Actions workflow files themselves.

## Adding a new Tool

Subclass `tools.base.Tool`:

- Implement `uses_plunger()` if the tool drives the mount's plunger axis
  (only `Pipette` does today) -- the base default is `False`.
- Override `on_attach(mount, robot)` / `on_detach()` for tool-specific setup
  or teardown, calling `super()` to preserve the base mount/robot
  associations unless you have a specific reason not to.
- If the tool should be configurable from `robot.yaml`'s `mounts:` section,
  add a `_build_<tool>(cfg)` function and a matching branch in
  `config.loader.load_robot`'s mount-building dispatch.
- Add `tests/test_tools/test_<name>.py`, following the pattern in
  `tests/test_tools/test_plunger_calibration.py` or `test_probe.py`.

## Adding a new routine Step

Subclass `routines.steps.Step`:

- Implement `execute(self, robot: Robot, side: MountSide) -> MountSide | None`.
  Return `None` unless the step changes the routine's active mount (only
  `SwitchMountStep` does today, returning the newly selected `MountSide` --
  see `Routine.run`, which propagates that return value to subsequent steps).
- Implement `describe(self) -> str` for dry-run output and routine
  inspection -- keep it a single human-readable line.
- Export the new step from `routines/__init__.py`.
- Add coverage in `tests/test_routines/test_steps.py`: construct a real
  `Robot(SimulatedTransport(), ...)`, call `execute()`, and assert on both
  the resulting G-code/position and `describe()`'s exact string.

Do not build a plugin registry or step-type dispatcher for this -- `Routine`
already treats every `Step` polymorphically through `execute`/`describe`;
a new step is just a new subclass, nothing else needs to know about it.
