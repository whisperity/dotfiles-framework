import os

from dotfiles.os import restore_working_directory


class RemoveCommandsMixin:
    """
    Provides a set of commonly usable "remove" actions for the installer.
    """

    def _expand(self, command):
        expander = getattr(self, "expand_args", None)
        if expander:
            command = expander(command)
        return command

    def __save_backup(self, *largs):
        saver = getattr(self, "_save_backup", None)
        if saver:
            return saver(*largs)

    @restore_working_directory
    def _removal(self, where, where_expanded, file_list, ignore_missing=True):
        if where_expanded:
            os.chdir(where_expanded)

        for file_original in file_list:
            unexpanded_file = os.path.join(where, file_original)
            real_file = os.path.join(where_expanded,
                                     self._expand(file_original))

            self.__save_backup(unexpanded_file, real_file)

            if os.path.isfile(real_file) or os.path.islink(real_file):
                try:
                    os.unlink(real_file)
                    print("\tDelete '%s'" % real_file)
                except FileNotFoundError:
                    if not ignore_missing:
                        raise
                    print("\tSkipDelete '%s': ENOENT" % real_file)

    def remove(self, file=None, files=None, where=None, ignore_missing=True):
        """
        Archives a file or set of files into the package's save, and then
        removes them from the system.

        If `where` is specified, the paths in `file` or `files` is considered
        relative from the `where`, which should be a directory.
        If it is not specified, the paths in `file` or `files` must be
        absolute paths.

        If `files` is specified, it is a list of file paths, and the behaviour
        is as if `remove()` was called for each file in `files`.
        """
        if file and files:
            raise NameError("Remove must specify either file or "
                            "files.")

        if where:
            where_expanded = self._expand(where)
            if os.path.abspath(where_expanded) != where_expanded:
                raise ValueError("'where' must be given as an absolute path")

            if file and not os.path.isdir(where_expanded):
                where_expanded = os.path.dirname(where_expanded)
                if not os.path.isdir(where_expanded):
                    raise NotADirectoryError("'where' must be an existing "
                                             "directory, when given.")

            if files and not os.path.isdir(where_expanded):
                raise NotADirectoryError("'where' must be an existing "
                                         "directory, when given.")
        else:
            where = ""
            where_expanded = ""
            for file_ in (files if files else [file]):
                file_ = self._expand(file_)
                if os.path.abspath(file_) != file_:
                    raise ValueError("If 'where' is not given, all 'files' "
                                     "(or 'file') must be an absolute path")

        self._removal(where, where_expanded, files if files else [file],
                      ignore_missing)
