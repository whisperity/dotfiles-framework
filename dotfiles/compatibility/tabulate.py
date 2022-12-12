import sys

try:
    from tabulate import tabulate
except ImportError:
    print("The tabulate package for the current Python interpreter cannot be "
          "loaded.\n"
          "Please run 'bootstrap.sh' from the directory of Dotfiles project "
          "to try and fix this.",
          file=sys.stderr)
    print("Will use a more ugly version of output tables as fallback...",
          file=sys.stderr)

    def tabulate(table, *args, **kwargs):
        """
        An ugly fallback for the table pretty-printer if 'tabulate' module is
        not available.
        """
        if 'headers' in kwargs:
            print('|', '        | '.join(kwargs['headers']), '       |')
        for row in table:
            for i, col in enumerate(row):
                row[i] = col.replace('\n', ' ')
            print('|', '        | '.join(row), '       |')
        return ""
