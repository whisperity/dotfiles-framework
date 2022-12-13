from collections import deque
from functools import wraps
import inspect
import os
import shutil
import sys

from dotfiles.os import restore_working_directory
from dotfiles.saved_data import get_user_save
from .base import _StageBase
from .shell_mixin import ShellCommandsMixin
from .remove_mixin import RemoveCommandsMixin


class Uninstall(_StageBase, ShellCommandsMixin, RemoveCommandsMixin):
    """
    The uninstall stage is responsible for clearing the package from the
    system, preferably to a state as if it was never installed.
    """
    def __init__(self, package, condition_checker, arg_expand):
        super().__init__(package, condition_checker)
        self.expand_args = arg_expand

    def remove_dirs(self, dirs):
        """
        Removes the specified directories from the system, if they are empty.
        """
        for dirp in map(self.expand_args, dirs):
            try:
                os.rmdir(self.expand_args(dirp))
                print("[DEBUG] Removed directory '%s'..." % dirp)
            except OSError as e:
                print("[WARNING] Removal of directory '%s' failed, because: "
                      "%s."
                      % (dirp, e), file=sys.stderr)

    def remove_tree(self, dir):
        """
        Removes the entire tree under 'dir'.
        The directory must exist, and must be a directory.
        """
        dirp = self.expand_args(dir)
        if not os.path.isdir(dirp):
            raise NotADirectoryError("'dir' must be an existing directory")

        print("[DEBUG] Removing tree under '%s'" % dirp)
        shutil.rmtree(dirp)

    def restore(self, file=None, files=None):
        """
        Restores a file or a set of files from the installed package's state
        backup to the real system.

        The paths in `file` or `files` must be absolute paths.

        If `files` is specified, it is a list of file paths, and the behaviour
        is as if `restore()` was called for each file in `files`.
        """
        if file and files:
            raise NameError("Restore must specify either file or "
                            "files.")

        for file in (files if files else [file]):
            file_ = self.expand_args(file)
            if os.path.abspath(file_) != file_:
                raise ValueError("All 'files' (or 'file') must be an "
                                 "absolute path")

        # FIXME: Inject this as a context.
        with get_user_save().get_package_archive(self.package.name) as zipf:
            for file_ in (files if files else [file]):
                file_real = self.expand_args(file_)
                try:
                    buffer = zipf.read(file_)
                    with open(file_real, 'wb') as target:
                        target.write(buffer)
                    print("[DEBUG] Restoring file '%s (%s)'..."
                          % (file_, file_real))
                except KeyError:
                    print("[WARNING] Won't restore '%s' as a corresponding "
                          "backup was not found for '%s'."
                          % (file_real, self.package.name),
                          file=sys.stderr)


def _wrap(fun):
    """
    Wraps the executed function with the action store logic for
    `_UninstallSignature`.
    """
    @wraps(fun)
    def _wrapper(*args, **kwargs):
        # Save the action's invocation.
        bind = inspect.signature(fun).bind(*args, **kwargs).arguments
        save_args = {k: bind[k]
                     for k in filter(lambda k: k != 'self', bind)}
        save_args['action'] = fun.__name__
        bind['self'].register_action(**save_args)

        return fun(*args, **kwargs)
    return _wrapper


class UninstallSignature:
    """
    `Uninstall` but without actually executing anything. This is used to store
    the uninstall actions that are automatically generated during installation
    of a package.
    """
    def __init__(self):
        self.actions = deque()

    def register_action(self, **kwargs):
        """
        Saves the specifed action to the stack of actions to be executed at
        uninstall.
        """
        args = {k.replace(' ', '_'): v for k, v in kwargs.items()}
        self.actions.appendleft(args)

    def pop(self):
        """
        Removes the last generated uninstall action from the list.
        """
        self.actions.popleft()

    # Developer note: keep the methods from `Uninstall` in sync without a body!

    @_wrap
    def remove_dirs(self, dirs):
        pass

    @_wrap
    def remove(self, file=None, files=None, where=None):
        pass

    @_wrap
    def remove_tree(self, dir):
        pass

    @_wrap
    def restore(self, file=None, files=None):
        pass
