from functools import wraps
import os


def restore_working_directory(fun):
    """
    Provides a method decorator that will restore the working directory of
    the executing Python interpreter to whatever it was when the method started
    executing.
    """
    @wraps(fun)
    def _wrapper(*args, **kwargs):
        cwd = os.getcwd()
        ret = None
        try:
            ret = fun(*args, **kwargs)
        finally:
            os.chdir(cwd)
        return ret
    return _wrapper


def umask(new_umask):
    """
    Provides a method decorator that will execute with the given new_umask set,
    and then restore the umask after the function has run.
    """
    def _decorator(fun):
        @wraps(fun)
        def _wrapper(*args, **kwargs):
            old_umask = os.umask(new_umask)
            ret = None
            try:
                ret = fun(*args, **kwargs)
            finally:
                os.umask(old_umask)
            return ret
        return _wrapper
    return _decorator


def _envvar_or_homedir(env_var, directory):
    return os.environ.get(env_var,
                          os.path.join(os.path.expanduser('~'), directory))


def cache_directory():
    """Returns the user-specific cache directory location."""
    return os.path.join(_envvar_or_homedir("XDG_CACHE_HOME", ".cache"),
                        "Dotfiles")


def config_directory():
    """Returns the user-specific configuration directory location."""
    return os.path.join(_envvar_or_homedir("XDG_CONFIG_HOME", ".config"),
                        "Dotfiles")


def data_directory():
    """Returns the user-specific persistent data directory location."""
    return os.path.join(_envvar_or_homedir("XDG_DATA_HOME", ".local/share"),
                        "Dotfiles")
