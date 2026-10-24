import io
import os
import sys
import types

import pytest

from udemy_transcripts import tui
from udemy_transcripts.tui import (BACKSPACE, DOWN, END, ENTER, ESC, HOME, SPACE, UP, Console)


def typed(text):
    return list(text)


def make_ui(keys, rows=24, cols=80):
    """Consola interactiva con teclas simuladas (se acaba la lista = fallo de la prueba)."""
    pending = list(keys)

    def read_key():
        assert pending, "el menú pidió más teclas de las previstas"
        return pending.pop(0)

    ui = Console(read_key=read_key, out=io.StringIO(), interactive=True,
                 size=lambda: os.terminal_size((cols, rows)))
    ui.pending = pending
    return ui


def numbered(answers):
    pending = list(answers)

    def input_fn(prompt):
        if not pending:
            raise EOFError
        return pending.pop(0)

    return Console(out=io.StringIO(), input_fn=input_fn, interactive=False)


# ---- listas con flechas -----------------------------------------------------------------
def test_choose_moves_with_arrows_and_wraps():
    assert make_ui([ENTER]).choose("T", ["a", "b", "c"]) == 0
    assert make_ui([DOWN, DOWN, ENTER]).choose("T", ["a", "b", "c"]) == 2
    assert make_ui([UP, ENTER]).choose("T", ["a", "b", "c"]) == 2          # da la vuelta
    assert make_ui([DOWN, DOWN, DOWN, ENTER]).choose("T", ["a", "b", "c"]) == 0
    assert make_ui([END, ENTER]).choose("T", ["a", "b", "c"]) == 2
    assert make_ui([END, HOME, ENTER]).choose("T", ["a", "b", "c"]) == 0


def test_choose_esc_goes_back_and_cursor_starts_where_asked():
    assert make_ui([ESC]).choose("T", ["a", "b"]) is None
    assert make_ui([ENTER]).choose("T", ["a", "b", "c"], cursor=2) == 2
    assert make_ui([ENTER]).choose("T", ["a", "b"], cursor=9) == 1          # se acota


def test_choose_draws_title_marker_and_hint_and_restores_the_cursor():
    ui = make_ui([ENTER])
    ui.choose("Mi título", ["uno", "dos"], hint="AYUDA")
    out = ui.out.getvalue()
    assert "Mi título" in out and "❯ uno" in out and "  dos" in out and "AYUDA" in out
    assert out.startswith("\x1b[?25l") and out.endswith("\x1b[?25h")


def test_multi_toggles_with_space():
    assert make_ui([SPACE, DOWN, DOWN, SPACE, ENTER]).multi("T", ["a", "b", "c"]) == [0, 2]
    assert make_ui([SPACE, ENTER]).multi("T", ["a", "b"], selected=[0]) == []   # desmarca
    assert make_ui([ENTER]).multi("T", ["a", "b"], selected=[1]) == [1]
    assert make_ui([ESC]).multi("T", ["a"]) is None
    out = make_ui([SPACE, ENTER])
    out.multi("T", ["a"])
    assert "[x] a" in out.out.getvalue()


def test_long_lists_scroll_and_still_reach_the_end():
    ui = make_ui([DOWN] * 20 + [ENTER], rows=12)
    assert ui.choose("T", [f"op{n}" for n in range(30)]) == 20
    out = ui.out.getvalue()
    assert "más" in out and "op20" in out


def test_empty_lists_do_not_wait_for_keys():
    assert make_ui([]).choose("T", []) is None
    assert make_ui([]).multi("T", []) == []


def test_confirm():
    assert make_ui([ENTER]).confirm("¿Seguro?") is True
    assert make_ui([DOWN, ENTER]).confirm("¿Seguro?") is False
    assert make_ui([ENTER]).confirm("¿Seguro?", default=False) is False
    assert make_ui([ESC]).confirm("¿Seguro?") is None


# ---- texto ---------------------------------------------------------------------------------
def test_ask_edits_the_line():
    assert make_ui(typed("ab") + [BACKSPACE] + typed("c") + [ENTER]).ask("Q") == "ac"
    assert make_ui(typed("a") + [SPACE] + typed("b") + [ENTER]).ask("Q") == "a b"
    assert make_ui([ENTER]).ask("Q", default="por defecto") == "por defecto"
    assert make_ui([ENTER]).ask("Q") == ""
    assert make_ui(typed("x") + [ESC]).ask("Q") is None


def test_ask_validates_and_asks_again():
    ui = make_ui(typed("mal") + [ENTER] + typed("bien") + [ENTER])
    assert ui.ask("Q", validate=lambda t: "no vale" if t == "mal" else None) == "bien"
    assert "no vale" in ui.out.getvalue()


def test_ask_secret_never_echoes():
    ui = make_ui(typed("secreto") + [ENTER])
    assert ui.ask("Token", secret=True) == "secreto"
    assert "secreto" not in ui.out.getvalue() and "*******" in ui.out.getvalue()


def test_ask_ignores_control_keys():
    assert make_ui([UP, DOWN] + typed("ok") + [ENTER]).ask("Q") == "ok"


# ---- respaldo numérico (terminal sin teclas) ------------------------------------------------
def test_numbered_choose():
    assert numbered(["2"]).choose("T", ["a", "b", "c"]) == 1
    assert numbered(["9", "x", "1"]).choose("T", ["a", "b"]) == 0           # repite si es inválido
    assert numbered([""]).choose("T", ["a", "b"]) is None
    assert numbered(["0"]).choose("T", ["a", "b"]) is None
    assert numbered([]).choose("T", ["a", "b"]) is None                      # EOF


def test_numbered_multi():
    assert numbered(["1,3"]).multi("T", ["a", "b", "c"]) == [0, 2]
    assert numbered([""]).multi("T", ["a", "b"], selected=[1]) == [1]
    assert numbered(["0"]).multi("T", ["a"]) is None
    assert numbered(["7", "2"]).multi("T", ["a", "b"]) == [1]


def test_numbered_ask_and_confirm_and_pause():
    ui = numbered(["texto"])
    assert ui.ask("Q") == "texto"
    assert numbered([""]).ask("Q", default="d") == "d"
    assert numbered([]).ask("Q") is None
    assert numbered(["1"]).confirm("¿?") is True
    numbered([]).pause()                                                    # EOF no falla
    ui = numbered(["mal", "bien"])
    assert ui.ask("Q", validate=lambda t: "no" if t == "mal" else None) == "bien"


def test_non_interactive_output_has_no_escape_codes():
    ui = numbered(["1"])
    ui.say("hola", tui.BOLD)
    ui.clear()
    ui.choose("T", ["a"])
    assert "\x1b" not in ui.out.getvalue()


# ---- teclas del sistema -----------------------------------------------------------------------
def test_plain_keys():
    assert [tui._plain_key(c) for c in ("\r", "\n", "\x1b", " ", "\x7f", "\b", "a")] == [
        ENTER, ENTER, ESC, SPACE, BACKSPACE, BACKSPACE, "a"]
    with pytest.raises(KeyboardInterrupt):
        tui._plain_key("\x03")


def test_windows_special_keys_come_in_two_parts(monkeypatch):
    chars = iter(["\xe0", "H", "\x00", "P", "\xe0", "Z", "x", "\r"])
    monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(getwch=lambda: next(chars)))
    assert [tui._read_key_windows() for _ in range(5)] == [UP, DOWN, "", "x", ENTER]


def test_enable_ansi_does_not_raise():
    assert isinstance(tui.enable_ansi(), bool)
