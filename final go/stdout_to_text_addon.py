bl_info = {
    "name": "Stdout/Stderr -> Text (Minimal)",
    "author": "you",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "Text Editor > Text datablock",
    "description": "Minimal redirect of Python stdout/stderr into a Blender Text datablock.",
    "category": "Development",
}

import bpy
import sys

TEXT_NAME = "PY_STDOUT.txt"
WRITE_THROUGH_TO_ORIGINAL = False


_ORIG_STDOUT = None
_ORIG_STDERR = None
_WRITER = None


def main_install():
    #step_get_text(TEXT_NAME)  # <-- only change: ensure text exists
    step_capture_original_streams()
    step_install_writer(TEXT_NAME, WRITE_THROUGH_TO_ORIGINAL)


def main_uninstall():
    step_uninstall_writer()


def step_capture_original_streams():
    global _ORIG_STDOUT, _ORIG_STDERR
    if _ORIG_STDOUT is None:
        _ORIG_STDOUT = sys.stdout
    if _ORIG_STDERR is None:
        _ORIG_STDERR = sys.stderr


def step_get_text(name: str) -> bpy.types.Text:
    txt = bpy.data.texts.get(name)
    if txt is None:
        txt = bpy.data.texts.new(name)
    return txt


def step_install_writer(text_name: str, write_through: bool):
    global _WRITER
    if _WRITER is not None:
        return

    _WRITER = step_make_writer(text_name, write_through)
    sys.stdout = _WRITER
    sys.stderr = _WRITER


def step_uninstall_writer():
    global _WRITER

    if _WRITER is not None:
        try:
            _WRITER.flush()
        except Exception:
            pass

    if _ORIG_STDOUT is not None:
        sys.stdout = _ORIG_STDOUT
    if _ORIG_STDERR is not None:
        sys.stderr = _ORIG_STDERR

    _WRITER = None


def step_make_writer(text_name: str, write_through: bool):
    class _Writer:
        def __init__(self):
            self.text_name = text_name
            self.write_through = write_through
            self.buf = ""

        def write(self, s):
            if not s:
                return 0

            self.buf += s
            if "\n" in self.buf:
                txt = step_get_text(self.text_name)
                parts = self.buf.split("\n")
                self.buf = parts.pop()
                for line in parts:
                    txt.write(line + "\n")

            if self.write_through:
                try:
                    if _ORIG_STDOUT:
                        _ORIG_STDOUT.write(s)
                except Exception:
                    pass

            return len(s)

        def flush(self):
            if self.buf:
                try:
                    step_get_text(self.text_name).write(self.buf)
                finally:
                    self.buf = ""

            if self.write_through:
                try:
                    if _ORIG_STDOUT:
                        _ORIG_STDOUT.flush()
                except Exception:
                    pass

    return _Writer()


def register():
    main_install()
    #bpy.app.timers.register(main_install, first_interval=0.1)//延迟0.1秒---def main_install()是不允许立刻执行

def unregister():
    main_uninstall()
