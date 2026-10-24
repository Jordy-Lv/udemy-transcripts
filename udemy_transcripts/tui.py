"""Terminal interactiva para el menú: flechas + Enter (y Esc para volver) o, si la terminal no
lo permite, el número de la opción.

Sin dependencias: lee las teclas con `msvcrt` (Windows) o `termios` (macOS/Linux) y dibuja con
secuencias ANSI, que PowerShell/Windows Terminal entienden. Todo pasa por `Console`, que recibe
el lector de teclas y la salida, así que las pantallas se prueban con teclas simuladas.
"""

import os
import shutil
import sys

UP, DOWN, LEFT, RIGHT = "up", "down", "left", "right"
HOME, END = "home", "end"
ENTER, ESC, SPACE, BACKSPACE = "enter", "esc", "space", "backspace"

_WIN_KEYS = {"H": UP, "P": DOWN, "K": LEFT, "M": RIGHT, "G": HOME, "O": END}
_ANSI_KEYS = {"[A": UP, "[B": DOWN, "[D": LEFT, "[C": RIGHT, "[H": HOME, "[F": END,
              "OA": UP, "OB": DOWN, "OD": LEFT, "OC": RIGHT, "OH": HOME, "OF": END}

BOLD, DIM, CYAN, GREEN, RED, RESET = ("\x1b[1m", "\x1b[2m", "\x1b[36m", "\x1b[32m", "\x1b[31m",
                                      "\x1b[0m")


def _plain_key(ch):
    if ch in ("\r", "\n"):
        return ENTER
    if ch == "\x1b":
        return ESC
    if ch == " ":
        return SPACE
    if ch in ("\x7f", "\b"):
        return BACKSPACE
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def _read_key_windows():
    import msvcrt
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):                       # tecla especial: el código viene aparte
        return _WIN_KEYS.get(msvcrt.getwch(), "")
    return _plain_key(ch)


def _read_key_posix():
    import select
    import termios
    import tty
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch = os.read(fd, 1).decode("utf-8", "replace")
        if ch == "\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                seq = os.read(fd, 2).decode("utf-8", "replace")
                return _ANSI_KEYS.get(seq, "")
            return ESC
        return _plain_key(ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def read_key():
    """Una tecla: UP/DOWN/…/ENTER/ESC/SPACE/BACKSPACE o el carácter escrito."""
    return _read_key_windows() if os.name == "nt" else _read_key_posix()


def enable_ansi():
    """¿La terminal entiende secuencias ANSI? En Windows activa el modo VT de la consola."""
    if os.name != "nt":
        return os.environ.get("TERM", "") not in ("", "dumb")
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.GetStdHandle(-11)                   # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))   # VT processing
    except (AttributeError, OSError, ImportError):
        return False


def detect_interactive():
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


class Console:
    """Entrada y salida del menú. `interactive=False` usa números y `input()`."""

    def __init__(self, read_key=None, out=None, input_fn=input, interactive=None, size=None):
        self.out = out or sys.stdout
        self._read_key = read_key or globals()["read_key"]
        self.input_fn = input_fn
        self.interactive = detect_interactive() if interactive is None else interactive
        if self.interactive and out is None and not enable_ansi():
            self.interactive = False
        self._size = size or (lambda: shutil.get_terminal_size((80, 24)))

    # ---- salida ---------------------------------------------------------------------------
    def write(self, text):
        self.out.write(text)
        self.out.flush()

    def say(self, text="", style=""):
        self.write((style + text + RESET if style and self.interactive else text) + "\n")

    def clear(self):
        if self.interactive:
            self.write("\x1b[2J\x1b[H")

    def pause(self, message="Pulsa Enter para continuar…"):
        try:
            if self.interactive:
                self.write(f"\n{DIM}{message}{RESET}")
                while self._read_key() != ENTER:
                    pass
                self.write("\n")
            else:
                self.input_fn(message + " ")
        except EOFError:
            pass

    # ---- listas ---------------------------------------------------------------------------
    def choose(self, title, options, cursor=0, hint="↑↓ mover · Enter elegir · Esc volver"):
        """Índice de la opción elegida, o None si se vuelve atrás (Esc)."""
        return self._pick(title, list(options), False, (), cursor, hint)

    def multi(self, title, options, selected=(),
              hint="↑↓ mover · Espacio marcar · Enter confirmar · Esc volver"):
        """Índices marcados (lista), o None si se vuelve atrás (Esc)."""
        return self._pick(title, list(options), True, selected, 0, hint)

    def confirm(self, question, default=True):
        answer = self.choose(question, ["Sí", "No"], 0 if default else 1,
                             hint="↑↓ mover · Enter elegir · Esc cancela")
        return None if answer is None else answer == 0

    def _pick(self, title, labels, multi, selected, cursor, hint):
        if not labels:
            return [] if multi else None
        if not self.interactive:
            return self._pick_numbered(title, labels, multi, selected)
        marks, cursor, top, drawn = set(selected), min(cursor, len(labels) - 1), 0, 0
        self.write("\x1b[?25l")
        try:
            while True:
                cols, rows = self._size()
                room = max(3, rows - 6 - len(title.split("\n")))
                top = min(max(top, cursor - room + 1), cursor) if len(labels) > room else 0
                frame = self._frame(title, labels, multi, marks, cursor, top, room, hint, cols)
                if drawn:
                    self.write(f"\x1b[{drawn}A\r\x1b[J")
                self.write("\n".join(frame) + "\n")
                drawn = len(frame)
                key = self._read_key()
                if key == UP:
                    cursor = (cursor - 1) % len(labels)
                elif key == DOWN:
                    cursor = (cursor + 1) % len(labels)
                elif key == HOME:
                    cursor = 0
                elif key == END:
                    cursor = len(labels) - 1
                elif key == SPACE and multi:
                    marks ^= {cursor}
                elif key == ENTER:
                    return sorted(marks) if multi else cursor
                elif key == ESC:
                    return None
        finally:
            self.write(f"\x1b[{drawn}A\r\x1b[J\x1b[?25h" if drawn else "\x1b[?25h")

    @staticmethod
    def _fit(text, cols):
        return text if len(text) < cols else text[:max(1, cols - 2)] + "…"

    def _frame(self, title, labels, multi, marks, cursor, top, room, hint, cols):
        lines = [f"{BOLD}{self._fit(line, cols)}{RESET}" for line in title.split("\n")] + [""]
        shown = range(top, min(len(labels), top + room))
        if top > 0:
            lines.append(f"{DIM}  ↑ {top} más{RESET}")
        for i in shown:
            box = ("[x] " if i in marks else "[ ] ") if multi else ""
            text = self._fit(f"{box}{labels[i]}", cols - 3)
            lines.append(f"{CYAN}{BOLD}❯ {text}{RESET}" if i == cursor else f"  {text}")
        if top + room < len(labels):
            lines.append(f"{DIM}  ↓ {len(labels) - top - room} más{RESET}")
        lines += ["", f"{DIM}{self._fit(hint, cols)}{RESET}"]
        return lines

    def _pick_numbered(self, title, labels, multi, selected):
        self.say(f"\n{title}")
        for n, label in enumerate(labels, 1):
            self.say(f"  {'*' if multi and n - 1 in selected else ' '}{n:>2}) {label}")
        ask = ("Números separados por coma (Enter = confirmar, 0 = volver): " if multi
               else "Elige un número (0 o Enter = volver): ")
        while True:
            try:
                answer = self.input_fn(ask).strip()
            except EOFError:
                return None
            if answer in ("0", "") and not (multi and answer == ""):
                return None
            try:
                if multi:
                    picks = sorted({int(x) - 1 for x in answer.replace(" ", "").split(",") if x}
                                   ) if answer else sorted(selected)
                    if all(0 <= p < len(labels) for p in picks):
                        return picks
                else:
                    n = int(answer) - 1
                    if 0 <= n < len(labels):
                        return n
            except ValueError:
                pass
            self.say("  Opción no válida.")

    # ---- texto ----------------------------------------------------------------------------
    def ask(self, prompt, default="", validate=None, secret=False):
        """Texto escrito, `default` si se deja vacío, o None si se cancela (Esc)."""
        suffix = f" [{default}]" if default and not secret else ""
        while True:
            text = self._read_line(f"{prompt}{suffix}: ", secret)
            if text is None:
                return None
            text = text.strip() or default
            error = validate(text) if validate and text else None
            if not error:
                return text
            self.say(f"  ✗ {error}", RED)

    def _read_line(self, prompt, secret):
        if not self.interactive:
            try:
                return self.input_fn(prompt)
            except EOFError:
                return None
        buf = ""
        self.write("\x1b[?25h")
        while True:
            self.write(f"\r\x1b[K{prompt}{'*' * len(buf) if secret else buf}")
            key = self._read_key()
            if key == ENTER:
                self.write("\n")
                return buf
            if key == ESC:
                self.write("\n")
                return None
            if key == BACKSPACE:
                buf = buf[:-1]
            elif key == SPACE:
                buf += " "
            elif len(key) == 1 and key.isprintable():
                buf += key
