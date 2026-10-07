# Changelog

Every release, what changed and where. Newest first.

Versions follow [semver](https://semver.org/). The browser extension has its own
numbering (`extension/*/manifest.json`) and changes independently of the app.

## [1.2.0] — 2026-10-07

The app now runs on Linux with no behavior change on Windows. Every
Windows-only layer maps to the native Linux equivalent; the shared logic
(gate, emergency flow, TickTick client, extension protocol) is untouched.

### Added (Linux)

- **`focuslock/service.py`** — systemd `--user` backend
  (`tickfence.service`, no root). New `python -m focuslock daemon` command
  runs the Engine with the guard armed, for `ExecStart`.
- **`focuslock/ipc.py`** — the same JSON protocol over a Unix socket at
  `XDG_RUNTIME_DIR/tickfence` instead of the named pipe.
- **`focuslock/paths.py`** — XDG data/config/runtime dirs on Linux;
  `ProgramData` on Windows unchanged.
- **`focuslock/shortcuts.py`, `focuslock/stub.py`** — `.desktop` launchers
  and `notify-send` block notices instead of `.lnk` and `MessageBox`.
- **`focuslock/store.py`** — no DPAPI on Linux: the token stays base64
  with `state.json` at `0600`.
- **`focuslock/rules.py`, `focuslock/guard.py`** — matching is stem-based
  (`firefox` == `firefox.exe`) and the Linux session core (gnome-shell,
  systemd, …) joins `NEVER_BLOCK`. There is no IFEO on Linux, so the
  process guard is the hard layer there.
- **`pyproject.toml`, `requirements.txt`** — `pywin32` is now gated on
  `sys_platform=='win32'`, so `pip install .` works on Linux.
- **`run_tests.sh`** — the same per-process suites as `run_tests.ps1`.

### Fixed (both platforms)

- **`focuslock/daemon.py`** — `_cmd_lock` used a bare `tr()` with no
  import, so activating the lock crashed inside the service handler.
- **`focuslock/daemon.py`, `focuslock/local.py`** — adding or removing
  blocked programs/sites never called `config.save()`; the lists lived
  only in memory and were lost on restart.

### Extension

- **1.4.0 is signed and installable.** The signed `.xpi` is linked from the
  README. The listing is unlisted, so it does not appear in addons.mozilla.org
  search; the README link is the way in.
- **`extension/chrome/manifest.json`, `extension/firefox/manifest.json`,
  `extension/*/popup.js`** — version to **1.4.0**. No source change since 1.3.1;
  the version is new because AMO rejects a re-upload of a version it already
  holds.
- **`extension/firefox/manifest.json`** — `gecko.id` stays
  `focuslock-agus@users.noreply.github.com`. The add-on was created on AMO before
  the rename and AMO ids are permanent, so a `tickfence-` id would mean a new
  listing with no reviews and no in-place updates for existing installs. AMO also
  rejects an upload whose manifest id differs from the one it has on file. The id
  is not shown to users; the manifest `name` is what appears in the browser.

### Known

- A user updating from the old FocusLock build keeps a 30-second alarm under the
  old `focuslock-poll` name. The code only acts on `tickfence-poll`, so it fires
  and does nothing, waking the background page for nothing. Clearing it on
  install is the fix and lands in a later extension version.

## [1.1.1] — 2026-10-02

### Fixed

- **`focuslock/reset.py`** — the command printed `Listo` and exited 0 while doing
  nothing. It wrote `state.json` with the service still running, and the service
  persisted its in-memory state over it about fourteen seconds later, so the lock
  came back. It now stops the service before writing, and if it cannot stop it,
  writes nothing, prints the commands to run, and exits 2.
- **`focuslock/service.py`** — added `is_running()`. `stop()` does not raise when
  it cannot stop the service; it exhausts its timeout and returns, which is why
  the caller had no way to tell success from failure.

### Tests

- **`tests/test_focuslock.py`** — four tests covering the above, with a service
  double whose `stop()` returns without stopping rather than raising.

### Housekeeping

- `pyproject.toml`, `installer/TickFence.iss`, `README.md` — version to 1.1.1.
- `AGENTS.md` — release-notes convention and the `git log <tag>..master` check.

## [1.1.0] — 2026-10-01

The Settings page rewrite, plus four bugs that only surfaced by running the app.

### Fixed

- **`focuslock/daemon.py`** — `_cmd_config_set` never called `config.save()`. Every
  setting changed in the GUI was lost when the service restarted.
- **`focuslock/config.py`** — `Config.save()` without a prior `load()` wrote `{}`,
  wiping the config including the token. `save()` now guards on having loaded.
- **`focuslock/rules.py`** — `python.exe`, `pythonw.exe` and `pythonservice.exe` were
  blockable. Locking the interpreter killed the GUI and left the lock on with no
  window. All three are in `NEVER_BLOCK`.
- **`focuslock/ui/emergency.py`** — the verdict was overwritten by the next refresh,
  so a rejected attempt showed no reason.
- **`focuslock/i18n.py`, `focuslock/ui/app.py`, `focuslock/__main__.py`,
  `focuslock/stub.py`, `focuslock/daemon.py`** — eight strings never went through
  `tr()`.
- **`focuslock/ui/app.py`** — the Settings page crushed its own fields at the real
  window width, so it is wrapped in a `QScrollArea`. Then the label column was
  rebuilt three times: one shared column, then fixed field widths, then labels
  centred on their field and right-aligned for a uniform gap. The QSS gap on
  `QFormLayout QLabel` plus `MinimumExpanding` is what puts the text at the
  vertical middle of the field.
- **`installer/TickFence.iss`** — missing `ArchitecturesInstallIn64BitMode`, so it
  installed to `Program Files (x86)`.
- **`installer/build.ps1`** — `install.log` was written in the console code page and
  came out with replacement characters.
- **`focuslock/build_xpi.py`** — `CONTENTS` was missing `i18n.js`.
- **`focuslock/__main__.py`** — a Python 3.12-only f-string broke the declared 3.11
  minimum.
- **`run_tests.ps1`** — swallowed tracebacks on failure.

### Added

- **`focuslock/i18n.py`** — English by default, Spanish available. The extension
  follows `navigator.language` instead of the app config.
- **`focuslock/shortcuts.py`** — `TickFence (dev)`, pointing at the project folder
  so edits show up without reinstalling.
- **`extension/chrome/i18n.js`, `extension/firefox/i18n.js`** and the popup and
  options pages — extension translation.
- **`CONTRIBUTING.md`**.

## [1.0.0] — 2026-09-29

First release.

### Added

- **`installer/TickFence.iss`, `installer/build.ps1`** — Inno Setup installer,
  one file one click. Needed a 3.12-only f-string fix and the 64-bit mode flag.
- **`.github/workflows/tests.yml`** — CI on Python 3.11 and 3.14.
- **`CONTRIBUTING.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/bug_report.md`**.
- **`docs/screenshots/`** — rendered from the real window, not placeholders.

### Changed

- Renamed FocusLock to TickFence across the service, `ProgramData`, the extension
  and the repository. The Python package stays `focuslock`: the service expects it.
- **Redesign** — neutral dark palette, left sidebar navigation, measured contrast.

### Changed behaviour worth knowing

- An empty TickTick project counts as finished work. Recurring tasks reset to `0`
  instead of archiving, so there is no pending→completed transition to observe;
  the app credits tasks that disappear from the project.