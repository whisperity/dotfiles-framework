import cmd
import errno
import sys

from dotfiles import sourcelist


def read_bool(prompt, default=True):
    default_txt = "[Y/n]" if default else "[y/N]"
    ret = input(prompt + " " + default_txt + " ")
    if ret == 'y' or ret == 'Y' or ret == '1':
        return True
    if ret == 'n' or ret == 'N' or ret == '0':
        return False
    if not ret:
        return default

    print("ERROR: Invalid choice, interpreting as 'No'.", file=sys.stderr)
    return False


class SourceListEditor(cmd.Cmd):
    intro = """
The source list editor is an interactive prompt that allows changing the
configuration file for the Dotfiles manager framework.
"""

    def __init__(self, sl_path):
        super().__init__()
        self.prompt = "(dotfiles-sourcelist) "
        self.status_changed = False
        self._filepath = sl_path
        self._sourcelist = None

    def do_load(self, arg):
        """Load the sources from the configuration file on the disk.

        This command is executed automatically when the editor starts, but can
        be used to discard the changes still pending.
        """
        if arg:
            print("ERROR: load() does not take any arguments.",
                  file=sys.stderr)
            return

        if self.status_changed:
            print("WARNING: Unsaved changes exist.")
            cont = read_bool("Continue?", False)
            if not cont:
                return

        print("Loading configuration from '%s'..." % self._filepath)
        try:
            self._sourcelist = sourcelist.SourceList(self._filepath)
            self.status_changed = False
        except Exception as e:
            print("Error: Failed to load: %s" % str(e), file=sys.stderr)

    def do_save(self, arg):
        """Save the changes to the configuration file on the disk."""
        if arg:
            print("ERROR: save() does not take any arguments.",
                  file=sys.stderr)
            return

        if not self.status_changed:
            return

        print("Saving configuration to '%s'..." % self._filepath)
        try:
            self._sourcelist.save()
            self.status_changed = False
        except Exception as e:
            print("Error: Failed to save: %s" % str(e), file=sys.stderr)

    def do_status(self, arg):
        """Fooo"""
        print("STATUS")
        print(arg)
        pass

    def do_change(self, arg):
        self.status_changed = True

    def postcmd(self, stop, line):
        self.prompt = "(dotfiles-sourcelist%s) " \
            % (" *" if self.status_changed else "")


def loop():
    """Start looping the interactive console for the editor."""
    if not sys.stdin.isatty():
        raise OSError(errno.EBADF, "Input isn't an interactive terminal.")

    ed = SourceListEditor(sourcelist.get_sourcelist_file())
    ed.cmdqueue = ["load", "status"]

    return ed.cmdloop()
