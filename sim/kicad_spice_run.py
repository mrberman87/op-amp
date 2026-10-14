#!/usr/bin/env python3
"""Run a SPICE deck through the ngspice shared library that KiCad's internal
simulator uses (libngspice.so.0), rather than the standalone `ngspice` binary.

KiCad's schematic simulator (eeschema -> Simulator) is a GUI around this same
shared library; driving it directly is the headless equivalent.

Usage:
    kicad_spice_run.py <deck.cir> <command> [<command> ...]

Example:
    kicad_spice_run.py from_sch_ol.cir op "ac dec 40 10 1gig" "wrdata /tmp/x.dat v(/OUT)"
"""
import ctypes, sys, os

_lib = ctypes.CDLL("libngspice.so.0")

_SendChar = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p)
_SendStat = _SendChar
_ControlledExit = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_bool,
                                   ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)
_SendData = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                             ctypes.c_int, ctypes.c_void_p)
_SendInitData = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                                 ctypes.c_void_p)
_BGThread = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_bool, ctypes.c_int, ctypes.c_void_p)

_log = []


@_SendChar
def _send_char(buf, ident, userdata):
    if buf:
        _log.append(buf.decode("utf-8", "replace"))
    return 0


@_SendStat
def _send_stat(buf, ident, userdata):
    if buf:
        _log.append(buf.decode("utf-8", "replace"))
    return 0


@_ControlledExit
def _controlled_exit(status, immediate, quiet, ident, userdata):
    return 0


@_SendData
def _send_data(data, n, ident, userdata):
    return 0


@_SendInitData
def _send_init(data, ident, userdata):
    return 0


@_BGThread
def _bg_thread(running, ident, userdata):
    return 0


_lib.ngSpice_Init.argtypes = [_SendChar, _SendStat, _ControlledExit,
                              _SendData, _SendInitData, _BGThread, ctypes.c_void_p]
_lib.ngSpice_Init.restype = ctypes.c_int
_lib.ngSpice_Command.argtypes = [ctypes.c_char_p]
_lib.ngSpice_Command.restype = ctypes.c_int
_lib.ngSpice_Circ.argtypes = [ctypes.POINTER(ctypes.c_char_p)]
_lib.ngSpice_Circ.restype = ctypes.c_int


def load(lines):
    arr = (ctypes.c_char_p * (len(lines) + 1))(
        *[ln.encode("utf-8") for ln in lines], None)
    return _lib.ngSpice_Circ(arr)


def command(cmd):
    rc = _lib.ngSpice_Command(cmd.encode("utf-8"))
    return rc


def run(deck, commands):
    with open(deck) as f:
        lines = [ln for ln in f.read().splitlines()]
    if not any(ln.strip().lower() == ".end" for ln in lines):
        lines.append(".end")
    _lib.ngSpice_Init(_send_char, _send_stat, _controlled_exit, _send_data,
                      _send_init, _bg_thread, None)
    rc = load(lines)
    if rc != 0:
        sys.stderr.write("ngSpice_Circ failed (rc=%d)\n" % rc)
        return rc
    for c in commands:
        command(c)
    command("quit")
    sys.stdout.write("".join(_log))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        sys.exit(2)
    deck = sys.argv[1]
    if os.path.dirname(deck):
        pass
    sys.exit(run(deck, sys.argv[2:]))
