#!/usr/bin/env python3

import argparse
import atexit
from collections import deque
from enum import Enum
import json
import subprocess
import sys

from dotfiles import condition_checker
from dotfiles import package
from dotfiles import temporary
from dotfiles import transformers
from dotfiles.argument_expander import package_glob
from dotfiles.lazy_dict import LazyDict
from dotfiles.saved_data import get_user_save, UserSave
from dotfiles.sourcelist import SourceList, get_sourcelist_file
from dotfiles.stages import Stages


if __name__ != "__main__":
    # This script is a user-facing entry point.
    raise ImportError("This script is a user-facing entry point and should not"
                      " be directly used as a module.")

# -----------------------------------------------------------------------------
# Implementation helper libraries.


class UserSaveContext:
    def __init__(self):
        self._instance = None

    def __enter__(self):
        try:
            self._instance = get_user_save()
            return self._instance
        except PermissionError:
            print("ERROR! Couldn't get lock on install information!",
                  file=sys.stderr)
            print("Another Dotfiles install running somewhere?",
                  file=sys.stderr)
            print("If not please execute: `rm -f %s` and try again."
                  % UserSave.lock_file, file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError:
            print("ERROR: User configuration file is corrupted.",
                  file=sys.stderr)
            print("It is now impossible to recover what packages were "
                  "installed.",
                  file=sys.stderr)
            print("Please remove configuration file with `rm %s` and try "
                  "again."
                  % UserSave.state_file, file=sys.stderr)
            print("Every package will be considered as if never installed.",
                  file=sys.stderr)
            sys.exit(1)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self._instance:
            self._instance.close()
            self._instance = None


class SourceListContext:
    def __init__(self):
        self._instance = None

    def __enter__(self):
        """Set up the source repositories as based on the user's configuration.
        """
        try:
            sl = SourceList(get_sourcelist_file())
            sl.load()
            sl.assemble()

            self._instance = sl
            return sl
        except Exception as e:
            print("ERROR! Couldn't load or set up the source management!",
                  file=sys.stderr)
            print(str(e), file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self._instance:
            self._instance = None

# -----------------------------------------------------------------------------
# Define command-line interface.


class Actions(Enum):
    NONE = 0
    LIST = 1
    INSTALL = 2
    UNINSTALL = 3

    EDITOR = 4


def argument_parser():
    parser = argparse.ArgumentParser(
        prog="dotfiles",
        description="""Installer program that handles installing user
                       environment configuration files and associated
                       tools.""")

    action = parser.add_argument_group("action arguments")
    action = action.add_mutually_exclusive_group()

    action.add_argument("--edit-sources",
                        dest="action",
                        action="store_const",
                        const=Actions.EDITOR,
                        help="""Start an interactive editor to configure the
                                sources Dotfiles will install packages
                                from.""")

    action.add_argument("-l", "--list",
                        dest="action",
                        action="store_const",
                        const=Actions.LIST,
                        default=False,
                        help="""Lists packages that could be installed from
                                the current sources in the order of configured
                                priority, or from the specified '--source'. In
                                addition, lists the currently installed
                                packages with the source set to 'INSTALLED'.
                                This is the default action if no package names
                                are specified.""")

    action.add_argument("-i", "--install",
                        dest="action",
                        action="store_const",
                        const=Actions.INSTALL,
                        default=False,
                        help="""Installs the specified packages, and its
                                dependencies. This is the default action if at
                                least one package name is specified.""")

    action.add_argument("-u", "--uninstall",
                        dest="action",
                        action="store_const",
                        const=Actions.UNINSTALL,
                        default=False,
                        help="""Uninstalls the specified packages, and other
                                packages that depend on them.""")

    parser.add_argument("package_names",
                        nargs='*',
                        metavar="package",
                        type=str,
                        help="""The name of the packages that should be
                                (un)installed. All subpackages in a package
                                group can be selected by saying 'group.*'.""")

    parser.add_argument("--source",
                        dest="pkg_source",
                        metavar="name",
                        type=str,
                        help="""The name of the configured package source to
                                use when installing or listing packages.
                                This option has no effect for the 'uninstall'
                                operation.
                                If specified, package will only be loaded and
                                installed from the named source.""")

    parser.add_argument("-s", "--simulate",
                        action="store_true",
                        help="""Do not execute any of the actions, but
                                simualte the traversal of the package graph
                                and what would happen.""")

    trform = parser.add_argument_group(
        "transformer arguments",
        """Transformers are automations that are executed before the real
           actions of a package descriptor and are meant to make **global**
           changes to the contents found within.""")

    trform.add_argument("--X-copies-as-symlinks",
                        dest="transform_copies_as_symlinks",
                        action="store_true",
                        help="""Execute (almost) all 'copy' actions as if they
                                were 'symlink' actions with the 'relative'
                                flag set. This allows changes to the deployed
                                system to be versioned back into the source
                                repository, if such is desired. If an action
                                must not be affected by this transformer,
                                it should be marked with the
                                '$transform.copies as symlinks: false'
                                option in the descriptor.""")

    return parser

# TODO: Support not clearing temporaries for debug purposes.

# TODO: Verbosity switch?

# -----------------------------------------------------------------------------


def fetch_packages(user_data, root_map):
    """
    Load the list of available packages from the given roots (and the
    installed package list) to the memory map.
    The packages themselves won't be parsed or instantiated, only the name
    storage is loaded.
    """

    def __package_factory(package_name):
        """
        Dispatches the actual creation of the `package.Package` instance for
        the given logical `package_name` to the appropriate factory method.
        """
        if user_data.is_installed(package_name):
            # If the package is installed, the data should be created from the
            # archive corresponding for the package's last install state.
            with user_data.get_package_archive(package_name) as zipf:
                return package.Package.create_from_archive(package_name, zipf)
        else:
            # If the package is not installed, load data from the repository.
            return package.Package.create(root_map, package_name)

    repository_packages = set(package.get_package_names(root_map))
    installed_packages = set(user_data.installed_packages)
    package_names = repository_packages | installed_packages

    return LazyDict(
        factory=__package_factory,
        initial_keys=package_names)


def expand_all_specified_packages(known_packages, specified_name_likes):
    return deque(package_glob(known_packages.keys(), specified_name_likes))


def check_for_invalid_packages(known_packages, specified_packages):
    """Die if the user specified a package that does not exist."""
    invalid_packages = [p for p in specified_packages
                        if p not in known_packages]
    if invalid_packages:
        print("ERROR: Specified to handle packages that are not "
              "available!",
              file=sys.stderr)
        print("  Not found:  %s" % ', '.join(invalid_packages),
              file=sys.stderr)
        sys.exit(1)


def check_permission(is_simulation, condition_results, condition, packages,
                     action_stage, action_verb):
    """
    Checks the given `condition` if the `packages` need them, storing the
    result in `condition_engine`.

    Returns
    -------
        Whether the condition was satisfied, and the list of packages that
        cannot be `action_verb`ed because of lack of condition.
    """
    packages_globally_needing_cond = \
        [p for p in packages
         if p.has_condition_directive(condition, Stages.NON_DESCRIPT)]
    packages_maybe_needing_cond = \
        [p for p in packages
         if p not in packages_globally_needing_cond
         and p.has_condition_directive(condition, action_stage)]

    if not packages_globally_needing_cond and \
            not packages_maybe_needing_cond:
        return None, list()

    print("PERMISSION CHECK: '%s'." % condition.value.IDENTIFIER)
    print("    %s\n" % condition.value.DESCRIPTION)

    if packages_globally_needing_cond:
        print("    The following packages *REQUIRE* this permission "
              "to be %sed:" % action_verb)
        print("        %s" % ' '.join(
            [p.name for p in packages_globally_needing_cond]))
    if packages_maybe_needing_cond:
        print("    The following packages _suggest_ this permission "
              "to be %sed, however, the %s might continue without it "
              "if the package's script has been prepared for the "
              "condition." % (action_verb, action_verb))
        print("        %s" % ' '.join(
            [p.name for p in packages_maybe_needing_cond]))

    if is_simulation:
        return True, list()

    satisfied = condition_results.check_and_store_if_new(condition)

    fails = list()
    if not satisfied:
        for package in packages_globally_needing_cond:
            print("WARNING: Refusing to %s '%s' as the required condition "
                  "'%s' was not adequately satisfied."
                  % (action_verb, package.name, condition.value.IDENTIFIER))
            fails.append(package)

    return satisfied, fails


def build_transformers(switches):
    transform_keys = [k.replace("transform_", '').title().replace('_', '')
                      for k, v in switches.items()
                      if k.startswith("transform_") and v]

    try:
        return list(map(lambda k: getattr(transformers, k)(True),
                        transform_keys)) + \
            [transformers.get_ultimate_transformer()]
        #    ^ This must always be appended for the necessary cleanup.
    except AttributeError as e:
        # FIXME: Python >= 3.10 has a nice "name" tag for the AttributeError
        # raise KeyError("Transformer '%s' implementation not found when "
        #                "loading" % str(e.name))
        raise KeyError("Transformer implementation not found when loading: %s"
                       % str(e))


# -----------------------------------------------------------------------------
# Entry point.

def _main():
    args = argument_parser().parse_args()

    if args.action == Actions.EDITOR:
        from dotfiles.actions import sourcelist_editor
        return sourcelist_editor.action()

    # Handle the default case if the user did not specify an action.
    if not args.action:
        if not args.package_names:
            args.action = Actions.LIST
        else:
            args.action = Actions.INSTALL

    if args.action == Actions.UNINSTALL and args.pkg_source:
        print("ERROR: Argument '--pkg-source' has no effect for uninstall.",
              file=sys.stderr)
        return 1

    if any(['internal' in name for name in args.package_names]):
        print("'internal' is a support package group that is not to be "
              "directly (un)installed, its life is restricted to helping "
              "other packages' installation process!", file=sys.stderr)
        return 1

    # Cleanup for (un)install temporaries.
    atexit.register(temporary.destroy_temporary_dir)

    with UserSaveContext() as user_data, SourceListContext() as source_manager:
        # Check if the user specified an explicit source root to use.
        package_roots = source_manager.filter_roots(args.pkg_source
                                                    if args.pkg_source
                                                    else None)
        known_packages = fetch_packages(user_data, package_roots)
        specified_packages = expand_all_specified_packages(known_packages,
                                                           args.package_names)
        check_for_invalid_packages(known_packages, specified_packages)

        if args.action == Actions.LIST:
            from dotfiles.actions import list_packages
            list_packages.action(known_packages, specified_packages)
            return 1

        action_class, action_stage, action_verb = None, None, None
        if args.action == Actions.INSTALL:
            from dotfiles.actions.install import Install
            action_class = Install
            action_stage = Stages.INSTALL
            action_verb = "install"
        elif args.action == Actions.UNINSTALL:
            from dotfiles.actions.uninstall import Uninstall
            action_class = Uninstall
            action_stage = Stages.UNINSTALL
            action_verb = "uninstall"
        if not action_class:
            raise NotImplementedError("Reached action execution without "
                                      "realising which action to run!")

        action = action_class(user_data, known_packages, specified_packages)
        action.setup_according_to_dependency_graph()
        if not action.packages:
            print("No packages need to be %sed." % action_verb)
            return 0

        condition_results = condition_checker.ConditionStore()
        for cond in condition_checker.Conditions:
            satisfied, fail_packages = \
                check_permission(args.simulate,
                                 condition_results,
                                 cond,
                                 list(action.package_objects),
                                 action_stage,
                                 action_verb)
            if not satisfied and fail_packages:
                for p in fail_packages:
                    action.uninvolve(p.name)
                    p.set_failed()

        transformers = build_transformers(vars(args))

        # Perform the actual action steps.
        return action.execute(args.simulate,
                              user_data,
                              condition_results,
                              transformers)


if __name__ == '__main__':
    sys.exit(_main())
