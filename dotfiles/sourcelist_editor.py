import cmd
import errno
import os
import subprocess
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
        self._exiting = False

    def postcmd(self, stop, line):
        self.prompt = "(dotfiles-sourcelist%s) " \
            % (" *" if self.status_changed else "")

        return self._exiting

    def emptyline(self):
        """Executed when the user just presses <ENTER>."""
        return self.do_status(None)

    def _complete_source_name(self, text, line, begidx, endidx):
        if not self._sourcelist:
            return

        return [entry.name for entry in self._sourcelist.sources
                if entry.name.startswith(text)]

    def do_load(self, arg):
        """Load the sources from the configuration file on the disk.

        This command is executed automatically when the editor starts, but can
        be used to discard the changes still pending.
        """
        if arg:
            print("ERROR: load() does not take any arguments.",
                  file=sys.stderr)
            return

        if self._sourcelist and self.status_changed:
            print("WARNING: Unsaved changes exist.")
            cont = read_bool("Continue?", False)
            if not cont:
                return

        print("Loading configuration from '%s'..." % self._filepath)
        try:
            self._sourcelist = sourcelist.SourceList(self._filepath)
            self._sourcelist.load()
            self.status_changed = False
        except Exception as e:
            print("Error: Failed to load: %s" % str(e), file=sys.stderr)

    def do_save(self, arg):
        """Save the changes to the configuration file on the disk."""
        if not self._sourcelist:
            print("ERROR: Can't 'save' if the list isn't loaded yet!",
                  file=sys.stderr)
            return
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

    def do_add(self, arg):
        """Asks the user to configure a single entry, and adds it to the list.
        """
        if not self._sourcelist:
            print("ERROR: Can't 'add' if the list isn't loaded yet!",
                  file=sys.stderr)
            return
        if arg:
            print("ERROR: add() does not take any arguments.",
                  file=sys.stderr)
            return

        print("The following kinds of source list entries are supported:")
        for entry_cls in sourcelist.SUPPORTED_ENTRIES:
            print("\t * %s: %s" % (entry_cls.type_key, entry_cls.help))
        print()
        type_choice = input("Please select the type of the entry: ")

        try:
            entry_cls = list(filter(lambda x: x.type_key == type_choice,
                                    sourcelist.SUPPORTED_ENTRIES))[0]
        except IndexError:
            print("ERROR: There is no source list entry kind '%s'"
                  % type_choice,
                  file=sys.stderr)
            return

        config = {"type": type_choice}
        for option in entry_cls.options:
            config[option.name] = option()

        correct = read_bool("Is the configured information correct?")
        if not correct:
            print("Not adding then.")
            return

        try:
            self._sourcelist.add_source(config)
            self.status_changed = True
        except Exception as e:
            print("Error: %s" % str(e), file=sys.stderr)

    def do_remove(self, arg):
        """Delete the entry with a particular name from the list."""
        if not self._sourcelist:
            print("ERROR: Can't 'remove' if the list isn't loaded yet!",
                  file=sys.stderr)
            return
        if not arg:
            print("ERROR: remove(name) requires the name of the entry to "
                  "remove.",
                  file=sys.stderr)
            return

        try:
            self._sourcelist.delete_source(arg)
            self.status_changed = True
        except Exception as e:
            print("Error: %s" % str(e), file=sys.stderr)

    def complete_remove(self, *args):
        return self._complete_source_name(*args)

    def do_down(self, arg):
        """Moves the package with the given name one step down the priority
        list.
        """
        if not self._sourcelist:
            print("ERROR: Can't 'up' if the list isn't loaded yet!",
                  file=sys.stderr)
            return
        if not arg:
            print("ERROR: down(name) requires the name of the entry to move.",
                  file=sys.stderr)
            return
        if self._sourcelist.num_sources < 2:
            print("Moving elements is only reasonable if there is at least "
                  "two.")
            return

        try:
            if self._sourcelist.swap_sources(arg, "DOWN"):
                self.status_changed = True
        except Exception as e:
            print("Error: %s" % str(e), file=sys.stderr)

    def complete_down(self, *args):
        return self._complete_source_name(*args)

    def do_up(self, arg):
        """Moves the package with the given name one step up the priority
        list.
        """
        if not self._sourcelist:
            print("ERROR: Can't 'up' if the list isn't loaded yet!",
                  file=sys.stderr)
            return
        if not arg:
            print("ERROR: up(name) requires the name of the entry to move.",
                  file=sys.stderr)
            return
        if self._sourcelist.num_sources < 2:
            print("Moving elements is only reasonable if there is at least "
                  "two.")
            return

        try:
            if self._sourcelist.swap_sources(arg, "UP"):
                self.status_changed = True
        except Exception as e:
            print("Error: %s" % str(e), file=sys.stderr)

    def complete_up(self, *args):
        return self._complete_source_name(*args)

    def do_edit(self, arg):
        """Opens the configuration file in an editor, instead of using the
        wizard.
        """
        if not self._sourcelist:
            print("ERROR: Can't 'edit' if the list isn't loaded yet!",
                  file=sys.stderr)
            return
        if arg:
            print("ERROR: edit() does not take any arguments.",
                  file=sys.stderr)
            return
        if self.status_changed:
            print("ERROR: Can't 'edit' if unsaved changes exist!",
                  file=sys.stderr)
            return

        editor = os.environ.get("VISUAL", os.environ.get("EDITOR", "vi"))
        subprocess.run([editor, self._filepath])
        self.cmdqueue.append("load")

    def do_status(self, arg):
        """Prints the currently configured sources."""
        if not self._sourcelist:
            print("ERROR: Can't 'status' if the list isn't loaded yet!",
                  file=sys.stderr)
            return

        if self.status_changed:
            print("Changes exist, which need to be saved with 'save'.",
                  file=sys.stderr)

        for idx, entry in enumerate(self._sourcelist.sources):
            print("\t%d. %s: %s" % (idx + 1, entry.name, str(entry)))

    def do_exit(self, arg):
        """Close the session."""
        if self._sourcelist and self.status_changed:
            print("WARNING: Unsaved changes exist.")
            cont = read_bool("Continue?", False)
            if not cont:
                return

        self._exiting = True


def loop():
    """Start looping the interactive console for the editor."""
    if not sys.stdin.isatty():
        raise OSError(errno.EBADF, "Input isn't an interactive terminal.")

    ed = SourceListEditor(sourcelist.get_sourcelist_file())
    ed.cmdqueue = ["load", "status"]

    return ed.cmdloop()
