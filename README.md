<div align="center">

# 🛡️ TickFence

**A focus blocker for Windows that keeps its promises.**

You decide which programs and which websites go dark.
You decide how many tasks in TickTick bring them back.
You decide how hard the emergency exit is to push.

</div>

<div align="center">

![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-0078D6?logo=windows&logoColor=white)
![python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![gui](https://img.shields.io/badge/GUI-PySide6-2D8BC0)
![tests](https://img.shields.io/badge/tests-278%20passing-16A34A)
![ci](https://github.com/zxkodas/TickFence/actions/workflows/tests.yml/badge.svg)
![chrome](https://img.shields.io/badge/Chrome%20%2F%20Edge%20%2F%20Brave-MV3-4285F4?logo=googlechrome&logoColor=white)
![firefox](https://img.shields.io/badge/Firefox-MV3-FF7139F?logo=firefoxbrowser&logoColor=white)
![service](https://img.shields.io/badge/enforcement-Windows%20Service%20%2B%20IFEO-6E7681)
![installer](https://img.shields.io/badge/installer-.exe-3D8B8B)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

---

TickFence locks itself to a task manager and will not let you skip the work.
It is **not** a parental control and it does not phone home. Everything runs on
your machine, under your account, against your own TickTick.

The whole thing is aimed at one specific moment: the ten seconds when you are
alone, unobserved, and deciding whether to cheat.

---

## 📸 What it looks like

**Everything is configurable.** This is the screen that decides how hard it
hits you — how many tasks, how long, how many words.

![Settings tab](docs/screenshots/04-ajustes.png)

**The main window.** The lock is off by default — it only turns on when you ask
for it, and it turns itself off as soon as the tasks are done:

![Main window](docs/screenshots/01-estado.png)

---

## 🎯 What it actually does

- 🔒 **Locking is opt-in.** Opening TickFence never blocks anything. Only the
  **Activate lock** button does. The whole point is that *you* start the clock.
- 🎯 **Credits come only from TickTick.** There is deliberately **no
  "mark as done" button** in TickFence — that shortcut would make the app
  pointless.
- 🚪 **The emergency exit exists**, and it is expensive on purpose: you write
  down *why*, and it is saved with a timestamp so you can read your own words
  back next time you are tempted.
- 🧠 **It works by making the block hard to undo**, not by nagging you. Windows
  itself refuses to launch the program.

---

## ⚙️ Make it yours

There are no magic numbers here. These are **defaults**, not rules — change
every one of them in *Ajustes*.

| Setting | Default | Range | What it decides |
|---|---:|---|---|
| Tasks needed to unlock | **2** | 1–50 | How much work buys your freedom |
| Polling interval | **45 s** | 15–600 s | How often TickTick is checked |
| Minimum pledge length | **300 words** | 50–5000 | How much you must write to get out |
| Minimum typing time | **5 min** | 1–120 | Anti-paste, anti-"I'll do it later" |
| Escape hatch duration | **20 min** | 1–480 | How long the emergency unlock lasts |
| Blocked programs | *(empty)* | — | What stops launching |
| Blocked sites | YouTube, Reddit, Instagram, X, Twitter, Twitch, Netflix, TikTok | — | What stops loading |
| Enable IFEO (hard block) | **on** | — | Turn it off and only the soft guard works |

**A gentle setup:** 1 task, 100 words, 1 minute.
**A brutal one:** 8 tasks, 1500 words, 30 minutes.

Both are the same program. Pick the one you will actually keep.

> **One real limitation, stated up front:** the app credits *any* task in the
> project, not tasks with a particular name. So pick a project that contains
> only study tasks — otherwise ticking a grocery item unlocks your evening.

---

## 🚀 Setup, step by step

### Step 0 — What you need

- Windows 10 or 11
- Python 3.11 or newer
- A free [TickTick](https://ticktick.com) account
- **One kanban project** for your tasks (board view, not a folder)

### Step 1 — Install the service

**The easy way:** download `TickFence-Setup-1.1.1.exe` from the
[releases page](https://github.com/zxkodas/TickFence/releases), run it, and
accept the Windows prompt. It asks for Administrator once, then does
everything below for you. It is **not code-signed**, so SmartScreen will warn
you; that warning is expected.

**Or from source**, in **PowerShell as Administrator**, in this folder:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Either way this installs dependencies, registers the Windows service, starts
it, and checks that it answers. You only do it once, and admin rights are only
needed that one time.

**On Linux**, there is no `.exe` and no admin needed. From this folder:

```bash
pip install .
python -m focuslock install
```

This installs the package, registers a **systemd user service**
(`tickfence.service`, no root), starts it, and checks that it answers. Two
honest differences from Windows: there is no IFEO on Linux, so programs are
stopped by the process guard instead of never starting; and the token is stored
base64 with `0600` permissions instead of DPAPI. Everything else — the poll
loop, the guard, the extension endpoint, the emergency flow — is the same.

### Step 2 — Get a TickTick token

1. Log in at [ticktick.com](https://ticktick.com)
2. Open the browser developer tools (**F12**)
3. Go to the **Network** tab, reload the page
4. Click any request to `api.ticktick.com`
5. Open **Headers → Authorization** and copy the part after `Bearer `

That is your token: a string starting with `tp_`.

> 🔐 **If you ever paste that token into a chat, a screenshot, or anywhere
> public — revoke it and make a new one.** A leaked token lets someone read and
> edit your tasks. TickFence stores it encrypted with DPAPI, but it cannot help
> you once the token has left your machine.

### Step 3 — Open the app

No admin rights needed from here on:

```powershell
python -m focuslock gui
```

### Step 4 — Paste the token

Go to the **Ajustes** tab:

1. Paste the token into **Token**
2. Click **Probar conexión y guardar**
3. A confirmation means TickTick answered and the token was saved encrypted

![Settings tab](docs/screenshots/04-ajustes.png)

### Step 5 — Name your project

Put your project name in **Proyecto de TickTick** — for example `Estudios`.

TickFence finds it **by name on every poll**, so if you later rename or recreate
the project, it keeps working. Any emoji TickTick puts in front of the name is
ignored.

### Step 6 — Decide how many tasks

Set **Lecturas necesarias** to the number you actually want. `2` is a fine
starting point; `1` if you are starting small; `5` if you need a real session.

### Step 7 — Decide how hard the exit is

In the **Emergencia** group:

- **Palabras mínimas** — how much you must write to get out
- **Minutos de escritura** — real typing time
- **Minutos que desbloquea** — how long the escape lasts before it re-locks

You can set this to something gentle and tighten it later. You can also tighten
it *while* a lock is active, which is a legitimate use.

### Step 8 — Choose what to block

**Programas** tab — add executables to **Bloqueados**:

![Programs tab](docs/screenshots/02-programas.png)

**Sitios** tab — add domains to **Bloqueados**:

![Sites tab](docs/screenshots/03-sitios.png)

Both tabs have a **Permitidos** list on the right that is never blocked. Put
your editor, your notes, your reference docs in there.

> 💡 Block by the exact executable name (`steam.exe`), not the shortcut.
> Click *Agregar* and pick from the list if you are unsure.

### Step 9 — Add the browser extension

TickFence shows the address it expects, under *Ajustes → Extensión del
navegador*. It looks like `http://127.0.0.1:47821/state?token=…`.

**Chrome / Edge / Brave**

1. `chrome://extensions` → turn on **Developer mode**
2. **Load unpacked** → select the `extension/chrome` folder
3. Open the extension's options, paste the address, save

> This loads from a folder, so moving or deleting the project folder stops it
> working. It survives browser restarts, not the folder being moved.

**Firefox**

Download the signed add-on (version 1.4.0):

<https://addons.mozilla.org/firefox/downloads/file/5079476/2c8d26177e6d412ebd94-1.4.0.xpi>

Install it with *Install Add-on From File*. **Permanent:** it survives browser
restarts and updates. The listing is currently unlisted, so it will not appear
when searching on addons.mozilla.org — the link above is how you get it.

Signing goes through [addons.mozilla.org](https://addons.mozilla.org/developers/)
and covers one version at a time, so any change to the extension needs a new
submission.

To work on the extension instead of installing the signed one:
`about:debugging#/runtime/this-firefox` → *Load Temporary Add-on* →
`extension/firefox/manifest.json`. That one is **removed every time you close
the browser**, so it is only for testing.

After changing the extension, rebuild the package with:

```powershell
python -m focuslock.build_xpi
```

**What a blocked site looks like.** The extension replaces the page with a
plain notice naming the app, how many tasks are still owed, and the two ways
out — finish the tasks, or use the emergency unlock.

### Step 10 — Start a session

Press **Activar bloqueo** in the *Estado* tab. From that moment:

- Blocked programs will not launch
- Blocked domains will not load
- Open tabs to those domains get closed
- The emergency button becomes available

Tick tasks in TickTick. When the counter reaches your target, it unlocks on its
own. You do not have to restart anything.

---

## 🚪 The emergency exit

If you need out and the tasks are not happening, press **Desbloqueo de
emergencia**. It asks for four things: first the pledge, then three questions
that are deliberately awkward to answer honestly.

| # | Field | Minimum |
|---|---|---|
| 1 | **The pledge** — *¿Por qué necesitás desbloquear ahora?* | *your configured word count* |
| 2 | **¿Por qué querés desbloquear ahora?** | 30 words |
| 3 | **¿Qué perdés si no lo hacés?** | 30 words |
| 4 | **¿Qué vas a hacer después?** | 30 words |

Plus a one-line summary that gets stored in the log.

Three details make this hard to fake, and they are deliberate:

- ⌨️ **It counts keystrokes, not characters.** Pasting a long text spikes the
  characters-per-keystroke ratio and it is rejected.
- ⏱️ **Time is measured between keystrokes.** A text sitting there waiting does
  not accumulate typing time.
- 🔌 **Closing the dialog does not reset the timer.** And a pause longer than
  15 minutes restarts the session.

If you get through, the block lifts for your configured window and the whole
thing is written to the **Bitácora** with a date:

![Log tab](docs/screenshots/06-bitacora.png)

When the window expires, the block returns by itself. Your words are still
there when it does.

---

## 🧱 How it works

```
┌─ Your normal session (no admin rights) ────────────┐
│    TickFence GUI  ──────named pipe──────┐          │
│    Browser extension ─────local HTTP────┤          │
└──────────────────────────────────────────┼──────────┘
                                           ▼
┌─ Windows service (LocalSystem, auto-start) ───────┐
│    · polls TickTick, awards credits                │
│    · writes / removes IFEO keys in HKLM            │
│    · process guard, every 0.8 s                    │
│    · local HTTP server for the extension           │
└───────────────────────────────────────────────────┘
```

The service owns the block. The GUI just asks it for things over a named pipe,
which is why **the GUI never needs admin rights**.

## 🧱 The three layers

| Layer | What it does | How it can be beaten |
|---|---|---|
| **IFEO** | Windows never starts the program — replaced by a notice | You would need admin to delete the `HKLM` keys |
| **Process guard** | Detects a process in 0.8 s and kills it if it slipped through | Killing it by hand from Task Manager |
| **Extension** | Blocks domains, closes tabs already open | Turning the extension off (yes, you can) |

The extension is the weakest layer, on purpose — there is no way to block an
extension from another process without the user noticing. **IFEO is what holds.**

### Why IFEO matters

`HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution
Options\<program>.exe` with a `Debugger` value makes Windows **not run** the
program. It runs the debugger instead. The program never loads, never paints a
window.

Because it lives in `HKLM`, a normal user cannot touch it. Removing it needs
elevation — which is exactly the point: **opening a console should not be
enough.**

## ⛔ What can never be blocked

> `rules.NEVER_BLOCK` is enforced **inside `match_program()` itself**. It is not
> part of your editable allowlist, so no setting can disable it.
>
> It covers the desktop shell (`explorer.exe`, `userinit.exe`, `sihost.exe`, …),
> the session core (`lsass.exe`, `csrss.exe`, `winlogon.exe`, `svchost.exe`, …),
> antivirus, TickFence itself, and the entire toolkit you would use to undo the
> block: `cmd.exe`, `powershell.exe`, `taskmgr.exe`, `regedit.exe`,
> `taskkill.exe`, `shutdown.exe`, `msconfig.exe`, `rundll32.exe`, `mshta.exe`,
> `wscript.exe`, `cscript.exe`.
>
> `explorer.exe` is **not** in the allowlist on purpose. The allowlist is
> editable; `NEVER_BLOCK` is not. If it were only in the allowlist, one day you
> would delete it by accident and lose your desktop.

This design came from a real bug: an earlier process guard killed
`explorer.exe` and took the whole desktop with it.

---

## 🖥️ Command reference

| Command | What it does |
|---|---|
| `python -m focuslock install [--token tp_…]` | Install and start the service (**admin**) |
| `python -m focuslock uninstall` | Remove service, IFEO keys, shortcuts (**admin**) |
| `python -m focuslock gui` | Open the window (no admin) |
| `python -m focuslock status` | One-line status |
| `python -m focuslock doctor` | **Full diagnostics — run this first** |
| `python -m focuslock reset` | Factory reset: unlocked, counters at zero |
| `python -m focuslock ifeo-reconcile` | Clean orphaned IFEO keys (service can be stopped) |
| `python -m focuslock console` | Run the engine in the foreground, **guard off** |

Run `doctor` first when something misbehaves: it reports the service state, the
IFEO keys, the pipe, the HTTP server, and whether the installed copy in
site-packages matches your working folder.

**Why `console` will not arm the guard.** It runs the engine **in your desktop
session**, not as a service. If the process guard ran there it would kill
programs in the session you are using — including your desktop. So it is off
unless you ask:

```powershell
python -m focuslock console --armar-guard
```

## 📍 Where things live

| What | Where |
|---|---|
| Configuration | `C:\ProgramData\TickFence\config.json` |
| State, credits, logs | `C:\ProgramData\TickFence\state.json` |
| TickTick token | inside `state.json`, **DPAPI-encrypted** |
| Service | `TickFenceSvc` — "TickFence Enforcement Service" |
| GUI ↔ service | `\\.\pipe\TickFence` |
| Extension endpoint | `http://127.0.0.1:47821/state?token=…` |
| Extensions | `extension/chrome/`, `extension/firefox/` |

You can also edit `config.json` by hand while the service is stopped.

## 🗂️ Project layout

```
focuslock/
  daemon.py     the engine: coordinates everything (runs as the service)
  gate.py       the gate: what counts as work and when it unlocks
  rules.py      normalisation and matching (tasks, sites, programs)
  ifeo.py       registry key writing and cleanup
  guard.py      the process guard
  server.py     local HTTP server for the extensions
  ipc.py        named pipe between GUI and service
  emergency.py  validation of the written pledge
  ticktick.py   API client (no third-party dependencies)
  store.py      persistent state
  config.py     configuration
  secrets.py    DPAPI encryption
  service.py    Windows service wrapper
  stub.py       the notice IFEO shows instead of your program
  paths.py      paths and platform checks
  local.py      non-service mode, for development
  diag.py       diagnostics
  reset.py      factory reset
  build_xpi.py  packaging for the browser extensions
  ui/           main window and emergency dialog
```

**`gate.py` is the heart and is isolated from I/O** — it takes a client and a
store, so the whole decision logic is testable without a network.

---

## 🧪 Tests

```powershell
.\run_tests.ps1          # all 8 suites, each in its own process
.\run_tests.ps1 -Quick   # skips test_guard, the slow one
```

**196 tests**, each suite in a separate process on purpose: `test_ui` creates a
`QApplication` and Qt allows only one per process.

| Suite | Covers |
|---|---|
| `test_focuslock` | Rules, the gate, the emergency flow, DPAPI, the HTTP server |
| `test_win32` | Scans the Win32 layer and the pywin32 module layout |
| `test_imports` | Valid imports, and that the UI only calls commands that exist |
| `test_ifeo` | Registry key construction and cleanup |
| `test_stub` | The block notice the stub shows |
| `test_ui` | **Builds the real window and tray**, headless |
| `test_extension` | Both extension manifests and the popup |
| `test_guard` | **Kills real processes**, verifies the `explorer.exe` protection |

---

## ⚠️ Known limits

- **The browser extension can be turned off.** IFEO cannot, but open tabs stay
  a back door while the browser runs.
- **The guard matches by process name.** Two versions of one app under
  different names need blocking both. And if one of them happens to be called
  `explorer.exe` or `OpenCode.exe`, TickFence will never touch it.
- **`console` is a development mode**, not a daily-use mode. Install the
  service for real use.
- **IFEO needs admin rights.** Without elevation the hard block is off and only
  the process guard works. `install.ps1` warns you.
- **The TickTick API is used as-is.** If TickTick changes its endpoints,
  `ticktick.py` needs updating. The project is matched by name precisely so a
  change of ID breaks nothing.
- **The service must be running.** Registry keys survive reboots, but with the
  service stopped there is no guard and no polling.
- **Deleting a TickTick task by hand counts as completing it.** Recurring tasks
  leave no other trace — see below.

### Why recurring tasks are tricky

When you tick a **recurring** TickTick task, it does not get archived. It resets
to `0` for the next day. There is no *pending → completed* transition left to
observe.

So TickFence also credits a task **that was registered and is now gone from the
project**. Completing every task in the project counts as finishing the work,
not as a glitch.

The trade-off is explicit: **deleting a task by hand also counts.** That is the
price of TickTick not exposing the completed state of a recurring task.

---

## 📋 Changelog

What changed in each version, and in which file: [`CHANGELOG.md`](CHANGELOG.md).

---

## 📜 License

**GPL-3.0-or-later.** See [`LICENSE`](LICENSE).

What that means in plain terms:

- ✅ Use it, study it, change it, improve it — anything.
- ✅ Share it, including commercially.
- ⚖️ **Any version you distribute must also be GPL-3.0, with the source.**
- ✍️ **The copyright notice and author must be kept.** If you fork this, the
  credit stays.
- 🚫 You may not sell a closed version of TickFence. That is the one thing GPL
  actually prevents.

**No license can forbid all commercial use.** GPL gets as close as an open
source license can, and it is the difference between "someone made a paid
private version of you" and "someone published their fork with your name on it."

If TickFence helps you and you end up changing it, I would genuinely like to
know. Not an obligation — just a thing that makes the work worth doing.

---

## 📝 Notes

- The interface ships in **English**; switch it in *Settings → Language*, and
  the app restarts. Code comments and docstrings are in **Spanish**, and this
  README is in **English**. That is deliberate, not an oversight.
- The browser extension follows your **system** language instead, because it
  does not read TickFence's config.
- Want to help? [`CONTRIBUTING.md`](CONTRIBUTING.md) has the rules that
  exist because breaking them took the author's desktop down.
