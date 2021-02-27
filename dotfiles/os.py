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
