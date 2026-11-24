"""Small, dependency-free terminal presentation for Desk."""

import os
import shutil
import sys
import textwrap


def _supports_color(stream):
    if not stream.isatty() or "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    if os.name == "nt":
        # Enable ANSI in classic PowerShell as well as Windows Terminal.
        try:
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.windll.kernel32
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = kernel.GetStdHandle(-12 if stream is sys.stderr else -11)
            mode = wintypes.DWORD()
            if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            return bool(kernel.SetConsoleMode(handle, mode.value | 0x0004))
        except (AttributeError, OSError):
            return False
    return True


class Terminal:
    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdout
        self.color = _supports_color(self.stream)

    @property
    def width(self):
        return max(12, min(96, shutil.get_terminal_size((80, 24)).columns - 2))

    def style(self, text, code):
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def detail(self, text):
        for line in textwrap.wrap(text, width=self.width - 2):
            print("  " + self.style(line, "90"), file=self.stream)

    def banner(self):
        print(file=self.stream)
        if self.width >= len("  DESK  /  Meridian Supply Co."):
            print("  " + self.style("DESK", "1;36") + "  /  Meridian Supply Co.", file=self.stream)
        else:
            print("  " + self.style("DESK", "1;36"), file=self.stream)
            self.detail("Meridian Supply Co.")
        self.detail("Orders, products & policies")
        print(file=self.stream)
        self.detail("/help  commands    /reset  new chat    /exit  leave")
        print("  " + self.style("-" * (self.width - 2), "90"), file=self.stream)
        print(file=self.stream)

    def prompt(self):
        return self.style("  You > ", "1;36")

    def assistant(self):
        print("\n  " + self.style("Desk", "1;32"), file=self.stream)

    def usage(self, sent, output, cached, latency, first_token, total_in, total_out,
              history, limit, attempts):
        first = f"{first_token:.2f}s" if first_token is not None else "n/a"
        print(file=self.stream)
        turn = f"Turn  {sent:,} in / {output:,} out"
        if cached:
            turn += f" ({cached:,} cached)"
        self.detail(f"{turn}  |  {latency:.2f}s total  |  {first} first token")
        session = (f"Session  {total_in:,} in / {total_out:,} out"
                   f"  |  History ~{history:,}/{limit:,} tokens")
        if attempts > 1:
            session += f"  |  {attempts} attempts"
        self.detail(session)
        print(file=self.stream)


class ReplyStream:
    """Wrap live text without buffering the answer or changing stored model text."""

    def __init__(self):
        self.terminal = Terminal()
        self.output = self.terminal.stream
        self.interactive = self.output.isatty()
        self.status = Terminal(sys.stderr)
        self.show_status = self.interactive and self.status.color
        self.column = 0
        self.pending_space = ""
        self.word = ""
        self.has_text = False
        if self.show_status:
            print(self.status.style("  Thinking...", "90"), end="", file=sys.stderr, flush=True)

    def _clear_status(self):
        if self.show_status:
            print("\r\033[2K", end="", file=sys.stderr, flush=True)
            self.show_status = False

    def write(self, chunk):
        self._clear_status()
        self.has_text = True
        if not self.interactive:
            print(chunk, end="", file=self.output, flush=True)
            return
        for char in chunk:
            if char.isspace():
                self._flush_word()
                if char == "\n":
                    print(self.pending_space, file=self.output, flush=True)
                    self.pending_space = ""
                    self.column = 0
                else:
                    self.pending_space += " " * (4 if char == "\t" else 1)
            else:
                self.word += char
                # Very long unbroken values still stream instead of waiting for whitespace.
                if len(self.word) >= self.terminal.width - 2:
                    self._flush_word()

    def _flush_word(self):
        if not self.word:
            return
        width = self.terminal.width - 2
        if self.column and self.column + len(self.pending_space) + len(self.word) > width:
            print(file=self.output)
            self.column = 0
            self.pending_space = ""
        if not self.column:
            print("  ", end="", file=self.output)
        # Bound indentation too, so a deeply indented line cannot overflow the terminal.
        space = self.pending_space[:max(0, width - self.column - len(self.word))]
        print(space + self.word, end="", file=self.output, flush=True)
        self.column += len(space) + len(self.word)
        self.pending_space = ""
        self.word = ""

    def finish(self):
        self._clear_status()
        self._flush_word()
        if self.has_text:
            print(self.pending_space, file=self.output, flush=True)
