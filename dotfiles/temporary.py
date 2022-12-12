"""
The Dotfiles installer needs to keep a temporary directory for any particular
execution session to share resources, environment and configuration between
the projects.
"""
import shutil
import tempfile

_DOTFILES_TEMP_DIR = None
_PACKAGE_TEMP_DIRS = {}


def temporary_dir():
    """
    Creates the session-wide ("global") temporary directory.
    :return: The path to the directory created (or the path to the one that
        previously exists.)
    """
    global _DOTFILES_TEMP_DIR
    if _DOTFILES_TEMP_DIR:
        return _DOTFILES_TEMP_DIR

    _DOTFILES_TEMP_DIR = tempfile.mkdtemp(prefix='dotfiles-')
    return _DOTFILES_TEMP_DIR


def has_temporary_dir():
    return _DOTFILES_TEMP_DIR is not None


def destroy_temporary_dir():
    if has_temporary_dir():
        shutil.rmtree(temporary_dir(), ignore_errors=True)


class TemporaryDir:
    """
    Allows the use of `temporary_dir` as a context manager.

    When exiting the context, the temporary directory is NOT(!) removed!
    """
    def __init__(self):
        self._temp_dir = None

    @property
    def dir(self):
        return self._temp_dir

    def __enter__(self):
        self._temp_dir = temporary_dir()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        return True


def package_temporary_dir(package_name):
    """
    Creates a temporary directory for the given package and returns the path
    to it.
    """
    package_dir = _PACKAGE_TEMP_DIRS.get(package_name, None)
    if not package_dir:
        with TemporaryDir() as root:
            package_dir = tempfile.mkdtemp(prefix=package_name + '-',
                                           dir=root.dir)
            _PACKAGE_TEMP_DIRS[package_name] = package_dir

    return package_dir
