#!/usr/bin/env python3

import argparse
import atexit
from collections import deque
from enum import Enum
import json
import subprocess
import sys

from dotfiles import package
from dotfiles import temporary
from dotfiles.argument_expander import package_glob
from dotfiles.sourcelist import SourceList, get_sourcelist_file
from dotfiles.condition_checker import ConditionChecker
from dotfiles.lazy_dict import LazyDict
from dotfiles.saved_data import get_user_save, UserSave


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


PARSER = argparse.ArgumentParser(
    prog='dotfiles',
    description="""Installer program that handles installing user environment
                   configuration files and associated tools.""")

ACTION = PARSER.add_argument_group("action arguments")
ACTION = ACTION.add_mutually_exclusive_group()

ACTION.add_argument("--edit-sources",
                    dest='action',
                    action='store_const',
                    const=Actions.EDITOR,
                    help="""Start an interactive editor to configure the
                            sources Dotfiles will install packages from.""")

ACTION.add_argument('-l', '--list',
                    dest='action',
                    action='store_const',
                    const=Actions.LIST,
                    default=False,
                    help="""Lists packages that could be installed from the
                            current sources in the order of configured
                            priority, or from the specified '--source'. In
                            addition, lists the currently installed packages
                            with the source set to 'INSTALLED'. This is the
                            default action if no package names are
                            specified.""")

ACTION.add_argument('-i', '--install',
                    dest='action',
                    action='store_const',
                    const=Actions.INSTALL,
                    default=False,
                    help="""Installs the specified packages, and its
                            dependencies. This is the default action if at
                            least one package name is specified.""")

ACTION.add_argument('-u', '--uninstall',
                    dest='action',
                    action='store_const',
                    const=Actions.UNINSTALL,
                    default=False,
                    help="""Uninstalls the specified packages, and other
                            packages that depend on them.""")

PARSER.add_argument('package_names',
                    nargs='*',
                    metavar='package',
                    type=str,
                    help="""The name of the packages that should be
                            (un)installed. All subpackages in a package group
                            can be selected by saying 'group.*'.""")

PARSER.add_argument("--source",
                    dest='pkg_source',
                    metavar='name',
                    type=str,
                    help="""The name of the configured package source to use
                            when installing or listing packages.
                            This option has no effect for the 'uninstall'
                            operation.
                            If specified, package will only be loaded and
                            installed from the named source.""")

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


def check_superuser():
    print("Testing access to the 'sudo' command, please enter your password "
          "as prompted.",
          file=sys.stderr)
    print("If you don't have superuser access, please press Ctrl-D.",
          file=sys.stderr)

    try:
        res = subprocess.check_call(
            ['sudo', '-p', "[sudo] password for user '%p' for Dotfiles: ",
             'echo', "sudo check successful."])
        return not res
    except Exception as e:
        print("Checking 'sudo' access failed!", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return False


# -----------------------------------------------------------------------------
# Handle executing the actual install steps.

def _install(known_packages, condition_engine, package_names):
    """
    Actually perform preparation and installation of the packages specified.
    """
    while package_names:
        print("-------------------=======================--------------------")
        instance = known_packages[package_names.popleft()]

        # Check if any dependency of the package has failed to install.
        for dependency in instance.dependencies:
            try:
                d_instance = known_packages[dependency]
                if d_instance.is_failed:
                    print("WARNING: Won't install '%s' as dependency '%s' "
                          "failed to install!"
                          % (instance.name, d_instance.name),
                          file=sys.stderr)
                    # Cascade the failure information to all dependents.
                    instance.set_failed()

                    break  # Failure of one dependency is enough.
            except KeyError:
                # The dependency found by the name isn't a real package.
                # This can safely be ignored.
                pass

        if instance.is_failed:
            print("Skipping '%s'..." % instance.name)
            continue

        print("Selecting package '%s'" % instance.name)
        instance.select()

        if instance.should_do_prepare:
            print("Performing pre-installation steps for '%s'..."
                  % instance.name)

        try:
            # (Prepare should always be called to advance the status of the
            # package even if it does not do any action.)
            instance.execute_prepare(condition_engine)
        except Exception as e:
            print("Failed to prepare '%s' for installation!"
                  % instance.name, file=sys.stderr)
            print(e)
            import traceback
            traceback.print_exc()

            instance.set_failed()
            continue

        try:
            print("Installing '%s'..." % instance.name)
            instance.execute_install(condition_engine)

            # Save the package's metadata and the current state of its
            # resource files into the user's backup archive.
            with get_user_save().get_package_archive(instance.name) as zipf:
                package.Package.save_to_archive(instance, zipf)
        except Exception as e:
            print("Failed to install '%s'!"
                  % instance.name, file=sys.stderr)
            print(e)
            import traceback

            traceback.print_exc()

            instance.set_failed()
            continue

        if instance.is_installed:
            print("Successfully installed '%s'." % instance.name)
            if not instance.is_support:
                get_user_save().save_status(instance)


def _uninstall(known_packages, condition_engine, package_names):
    """
    Actually perform removal of the packages specified.
    """
    while package_names:
        print("-------------------=======================--------------------")
        instance = known_packages[package_names.popleft()]
        print("Selecting package '%s'" % instance.name)

        if not instance.has_uninstall_actions:
            print("Nothing to do for uninstall of '%s'." % instance.name)
            continue

        try:
            print("Removing '%s'..." % instance.name)
            instance.execute_uninstall(condition_engine)
        except Exception as e:
            print("Failed to uninstall '%s'!"
                  % instance.name, file=sys.stderr)
            print(e)
            import traceback

            traceback.print_exc()

            instance.set_failed()
            continue

        if not instance.is_installed:
            print("Successfully uninstalled '%s'." % instance.name)
            get_user_save().save_status(instance)


# -----------------------------------------------------------------------------
# Entry point.

def _main():
    args = PARSER.parse_args()

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

        action_class, action_verb = None, None
        if args.action == Actions.INSTALL:
            from dotfiles.actions.install import Install
            action_class = Install
            action_verb = "install"
        elif args.action == Actions.UNINSTALL:
            from dotfiles.actions.uninstall import Uninstall
            action_class = Uninstall
            action_verb = "uninstall"
        if not action_class:
            raise NotImplementedError("Reached action execution without "
                                      "realising which action to run!")

        action = action_class(user_data, known_packages, specified_packages)
        action.setup_according_to_dependency_graph()
        if not action.packages:
            print("No packages need to be %sed." % action_verb)
            return 0


        packages_to_handle = specified_packages

    print("ERROR: The project is under refactoring, parts of the execution "
          "may not normally continue...", file=sys.stderr)
    sys.exit(69)

    # -------------------------------------------------------------------------
    # Check if any package to install/uninstall needs superuser to do so.
    requires_superuser = set()
    suggests_superuser = set()
    for name in list(packages_to_handle):  # Work on copy, iteration modifies.
        instance = known_packages[name]
        if instance.requires_superuser:
            requires_superuser.add(name)
        else:
            if args.action == Actions.INSTALL and \
                    instance.suggests_superuser_install:
                suggests_superuser.add(name)
            elif args.action == Actions.UNINSTALL and \
                    instance.suggests_superuser_uninstall:
                suggests_superuser.add(name)

    if requires_superuser:
        print("The following packages *REQUIRE* superuser access to be "
              "managed:")
        print("\t%s" % ' '.join(requires_superuser))
    if suggests_superuser:
        print("The following packages suggest superuser access for "
              "management, but (un)installation might continue without it. "
              "Usually, the package's install code contains additional "
              "optional steps, such as (un)installing system-wide "
              "dependencies.")
        print("\t%s" % ' '.join(suggests_superuser))

    condition_engine = ConditionChecker()
    if requires_superuser or suggests_superuser:
        has_superuser = check_superuser()
        if not has_superuser:
            for name in requires_superuser:
                print("WARNING: Won't manage '%s' as user presented no "
                      "superuser access!" % name, file=sys.stderr)
                instance = known_packages[name]
                instance.set_failed()
        else:
            condition_engine.set_superuser_allowed()

    # Perform the actual modification steps.
    if args.action == Actions.INSTALL:
        print("Will INSTALL the following packages:\n        %s"
              % ' '.join(sorted(packages_to_handle)))
        _install(known_packages, condition_engine, packages_to_handle)
    elif args.action == Actions.UNINSTALL:
        print("Will REMOVE the following packages:\n        %s"
              % ' '.join(sorted(packages_to_handle)))
        _uninstall(known_packages, condition_engine, packages_to_handle)


if __name__ == '__main__':
    sys.exit(_main())
