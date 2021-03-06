"""Compatibility loader which loads some sort of a YAML interpreter, or kills
the process if it can't be done."""

# flake8: noqa

try:
    from yaml import YAMLError
    from yaml import load as load_yaml
    from yaml import dump as dump_yaml

    try:
        # Get the faster version of the loader, if possible.
        from yaml import CSafeLoader as Loader
        from yaml import CSafeDumper as Dumper
    except ImportError:
        # NOTE: Installing "LibYAML" requires compiling from source, so in
        # case the current environment does not have it, just fall back to
        # the pure Python (thus slower) implementation.
        from yaml import SafeLoader as Loader
        from yaml import SafeDumper as Dumper
except ImportError:
    import sys
    print("The YAML package for the current Python interpreter cannot be "
          "loaded.\n"
          "Please run 'bootstrap.sh' from the directory of Dotfiles project "
          "to try and fix this error.",
          file=sys.stderr)
    sys.exit(-1)
