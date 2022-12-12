import fnmatch
import os
import pprint
import shutil
import zipfile

from dotfiles import yaml
from dotfiles.argument_expander import ArgumentExpander
from dotfiles.condition_checker import Conditions
from dotfiles.os import restore_working_directory
from dotfiles.status import Status, require_status
from dotfiles.temporary import package_temporary_dir, temporary_dir


K_LONG_DESCRIPTION = "description"

K_DEPENDENCIES = "dependencies"

K_SUPPORT_BOOL = "support"
K_SUPPORT_HARDCODED_NAME = "internal"

K_WILL_AUTO_INSTALL_PARENT = "depend on parent"

K_CONDITIONAL_POSITIVE = "if"
K_CONDITIONAL_NEGATIVE = "if not"

K_PREPARE = "prepare"
K_INSTALL = "install"
K_UNINSTALL_GENERATED = "generated uninstall"
K_UNINSTALL_USER_DEFINED = "uninstall"


class ExecutorError(Exception):
    """
    Indicates that an error happened during execution of a command from the
    package descriptor.
    """
    def __init__(self, package, stage, action):
        super().__init__()
        self.package = package
        self.stage = stage
        self.action = action

    def __str__(self):
        return "Execution of %s action for %s failed.\n" \
               "Details of action:\n%s" \
               % (self.stage, str(self.package), pprint.pformat(self.action))


class PackageMetadataError(SystemError):
    """
    Indicates that a package's metadata 'package.yaml' file is semantically
    incorrect.
    """
    def __init__(self, package, msg):
        super().__init__()
        self.package = package
        self.msg = msg

    def __str__(self):
        return "%s 'package.yaml' invalid: %s" % (str(self.package), self.msg)


class Package:
    """
    Describes a package that the user can "install" to their system.

    Packages are stored in the 'packages/' directory in a hierarchy: directory
    names are translated as '.' separators in the logical package name.

    Each package MUST contain a 'package.yaml' file that describes the
    package's meta information and commands that are executed to configure and
    install the package.

    The rest of this package directory is ignored by the script.
    """

    @classmethod
    def package_name_to_data_file(cls, root_path, name):
        """
        Convert the package logical name to the datafile path under the
        given package root_path.
        """
        return os.path.join(root_path,
                            name.replace('.', os.sep),
                            'package.yaml')

    @classmethod
    def data_file_to_package_name(cls, root, path):
        """
        Extract the name of the package from the file path of the package's
        metadata file.
        """
        return os.path.dirname(path) \
            .replace(root, '', 1) \
            .replace(os.sep, '.') \
            .lstrip('.')

    def __init__(self, root_name, root_path, logical_name, datafile_path):
        self.root = root_name
        self._root_path = root_path
        self.name = logical_name
        self.datafile = datafile_path
        self.resource_dir = os.path.dirname(datafile_path)
        self._status = Status.NOT_INSTALLED

        # Optional callable, fetches resources. By default, not implemented.
        # (via https://stackoverflow.com/a/8294654)
        self._load_resources = lambda: (_ for _ in ()).throw(
            NotImplementedError("_load_resources wasn't specified."))

        self._teardown = []

        with open(datafile_path, 'r') as datafile:
            self._data = yaml.load_yaml(datafile, Loader=yaml.Loader)
            if not self._data:
                self._data = dict()

        self._expander = ArgumentExpander()
        self._expander.register_expansion('PACKAGE_DIR', self.resource_dir)
        self._expander.register_expansion('SESSION_DIR', temporary_dir())

        # Validate package YAML structure.
        # TODO: This list of error cases is not full.
        if self.is_support and self.has_uninstall:
            raise PackageMetadataError(self,
                                       "Package marked as a support but has "
                                       "an 'uninstall' section!")

    @classmethod
    def create(cls, root_map, logical_name):
        """
        Creates a `Package` instance for the given logical package name,
        using the package sources specified in the root_map.
        """
        datafile = None
        for root, root_path in root_map.items():
            used_root_name, used_root_path = root, root_path
            datafile = Package.package_name_to_data_file(used_root_path,
                                                         logical_name)
            if os.path.isfile(datafile):
                # We found the *first* root to load the package from under.
                break

        if not datafile:
            raise KeyError("Package data file for '%s' was not found."
                           % logical_name)

        try:
            instance = Package(used_root_name, used_root_path, logical_name,
                               datafile)

            # A package loaded from the disk doesn't need anything extra
            # to load its resources.
            instance.__setattr__('_load_resources', lambda: None)

            return instance
        except FileNotFoundError:
            raise KeyError("Package data file for '%s' was not found."
                           % logical_name)
        except yaml.YAMLError:
            raise ValueError("Package data file for '%s' is corrupt."
                             % logical_name)

    @classmethod
    def create_from_archive(cls, logical_name, archive):
        """
        Creates a `Package` instance using the information and resources found
        in the given `archive` (which must be a `zipfile.ZipFile` instance).
        """
        if not isinstance(archive, zipfile.ZipFile):
            raise TypeError("'archive' must be a `ZipFile`")

        # Unpack the metadata file to a temporary directory.
        package_dir = package_temporary_dir(logical_name)
        archive.extract('package.yaml', package_dir)

        instance = Package('', '', logical_name,
                           os.path.join(package_dir, 'package.yaml'))
        instance.__setattr__('_status', Status.INSTALLED)

        def _load_resources():
            """
            Helper function that will extract the resources of the package
            to the temporary directory when needed.
            """
            with zipfile.ZipFile(archive.filename, 'r') as zipf:
                for file in zipf.namelist():
                    if not file.startswith('$PACKAGE_DIR/'):
                        continue

                    zipf.extract(file, package_dir)

                    # Temporary is extracted by keeping the '$PACKAGE_DIR/'
                    # directory, thus it has to be moved one level up.
                    without_prefix = file.replace('$PACKAGE_DIR/', '', 1)
                    os.makedirs(
                        os.path.join(package_dir,
                                     os.path.dirname(without_prefix)),
                        exist_ok=True)
                    shutil.move(os.path.join(package_dir, file),
                                os.path.join(package_dir, without_prefix))
            shutil.rmtree(os.path.join(package_dir, '$PACKAGE_DIR'),
                          ignore_errors=True)

            # Subsequent calls to self._load_resources() shouldn't do anything.
            instance.__setattr__('_load_resources', lambda: None)

        instance.__setattr__('_load_resources', _load_resources)

        return instance

    @classmethod
    def save_to_archive(cls, package, archive):
        """
        Saves the given `package`'s resources(including the potential
        generated configuration) into the given `archive` (of type
        `zipfile.ZipFile`).
        """
        if not isinstance(archive, zipfile.ZipFile):
            raise TypeError("'archive' must be a `ZipFile`")

        for dirpath, _, files in os.walk(package.resource_dir):
            arcpath = dirpath.replace(package.resource_dir, '$PACKAGE_DIR', 1)
            if 'package.yaml' in files:
                package_name_for_yaml = \
                    Package.data_file_to_package_name(
                        package.root_path,
                        os.path.join(dirpath, 'package.yaml'))
                if package_name_for_yaml != package.name:
                    # A subpackage was encountered, which should not be
                    # saved to the current package's archive.
                    continue

            for file in files:
                if file == 'package.yaml':
                    # Do not save 'package.yaml', the serialized memory
                    # will be saved instead.
                    continue

                archive.write(os.path.join(dirpath, file),
                              os.path.join(arcpath, file),
                              compress_type=zipfile.ZIP_DEFLATED)

        archive.writestr('package.yaml', package.serialize(),
                         compress_type=zipfile.ZIP_DEFLATED)

    @property
    def root_path(self):
        """Returns the path of the package source root where the package
        was created from, if any.

        Note
        ----
            This value depends on user configuration and is to be consider
            transient even between Dotfiles invocations, and as such,
            should **NOT** be saved!
        """
        return self._root_path

    @require_status(Status.NOT_INSTALLED, Status.INSTALLED)
    def serialize(self):
        """
        Return the package's data in YAML string format.
        """
        return yaml.dump_yaml(self._data, Dumper=yaml.Dumper)

    @property
    def status(self):
        """
        Returns the `Status` value associated with the package.
        """
        return self._status

    @property
    def is_installed(self):
        return self._status == Status.INSTALLED

    @property
    def is_failed(self):
        return self._status == Status.FAILED

    @property
    def description(self):
        """
        An arbitrary description from the package metadata file that can be
        presented to the user.
        """
        return self._data.get(K_LONG_DESCRIPTION, None)

    def has_condition_directive(self, condition, for_status=Status.ANY):
        """
        Returns if the current package mentions the `condition` in its
        descriptor, in the context of status given as `for_status`.
        """
        def _check_elem(e):
            if type(e) is not dict:
                raise TypeError("Expected dict in _check_elem.")
            required = e.get(K_CONDITIONAL_POSITIVE, [])
            anti_required = e.get(K_CONDITIONAL_NEGATIVE, [])
            return condition.value.IDENTIFIER in required or \
                condition.value.IDENTIFIER in anti_required

        def _check_list(li):
            if type(li) is not list:
                raise TypeError("Expected list in _check_list.")
            return any(map(_check_elem, li))

        if for_status == Status.ANY:
            return _check_elem(self._data)
        if for_status == Status.NOT_INSTALLED:
            # If the **request** is to check in the status of "not installed",
            # check for requirements of installation.
            return _check_elem(self._data) or \
                _check_list(self._data.get(K_PREPARE, [])) or \
                _check_list(self._data.get(K_INSTALL, []))
        if for_status == Status.INSTALLED:
            # If the **request** is to check in the status of "installed",
            # check for requirements of uninstallation.
            return _check_elem(self._data) or \
                _check_list(self._data.get(K_UNINSTALL_USER_DEFINED, [])) or \
                _check_list(self._data.get(K_UNINSTALL_USER_DEFINED, []))

    @property
    def is_support(self):
        """
        Whether or not a package is a "support package".

        Support packages are fully featured packages in terms of having prepare
        and install actions, but they are not meant to write anything permanent
        to the disk.

        Note that the Python code does NOT sanitise whether or not a package
        marked as a support package actually conforms to the rule above.
        """
        return self._data.get(K_SUPPORT_BOOL, False) or \
            K_SUPPORT_HARDCODED_NAME in self.name

    @property
    def depends_on_parent(self):
        """
        Whether the package depends on its parent package in the logical
        hierarchy.
        """
        return self._data.get(K_WILL_AUTO_INSTALL_PARENT, True)

    @property
    def parent(self):
        """
        Returns the logical name of the package that SHOULD BE the parent
        package of the current one.

        There are no guarantees that the name actually refers to an
        installable package.
        """
        return '.'.join(self.name.split('.')[:-1])

    @property
    def dependencies(self):
        """
        Get the list of all dependencies the package metadata file describes.

        There are no guarantees that the packages named actually refer to
        installable packages.
        """
        return self._data.get(K_DEPENDENCIES, []) + \
            ([self.parent] if self.depends_on_parent and self.parent
             else [])

    @require_status(Status.NOT_INSTALLED)
    def select(self):
        """
        Mark the package selected for installation.
        """
        self._status = Status.MARKED

    def set_failed(self):
        """
        Mark that the execution of package actions failed.
        """
        self._status = Status.FAILED

    @property
    def has_prepare(self):
        """
        :return: If there are pre-install actions present for the current
        package.
        """
        return K_PREPARE in self._data

    @require_status(Status.MARKED)
    @restore_working_directory
    def execute_prepare(self, condition_checker):
        if not self.has_prepare:
            self._status = Status.PREPARED
            return

        from dotfiles.stages.prepare import Prepare
        executor = Prepare(self,
                           condition_checker,
                           self._expander)
        self._expander.register_expansion('TEMPORARY_DIR',
                                          executor.temp_path)
        # Register that temporary files were created and should be
        # cleaned up later.
        self._teardown.append(getattr(executor, '_cleanup'))

        # Start the execution from the temporary download/prepare folder.
        os.chdir(executor.temp_path)

        self._load_resources()

        for step in self._data.get(K_PREPARE):
            if not executor(**step):
                self.set_failed()
                raise ExecutorError(self, K_PREPARE, step)

        self._status = Status.PREPARED

    @require_status(Status.PREPARED)
    @restore_working_directory
    def execute_install(self, condition_checker):
        from dotfiles.stages.install import Install
        from dotfiles.stages.uninstall import UninstallSignature

        uninstall_generator = UninstallSignature()
        executor = Install(self,
                           condition_checker,
                           self._expander,
                           uninstall_generator)

        # Start the execution in the package resource folder.
        self._load_resources()
        os.chdir(self.resource_dir)

        for step in self._data.get(K_INSTALL):
            if not executor(**step):
                self.set_failed()
                raise ExecutorError(self, K_INSTALL, step)

        self._status = Status.INSTALLED

        if uninstall_generator.actions:
            # Save the uninstall actions to the package's data.
            self._data[K_UNINSTALL_GENERATED] = \
                list(uninstall_generator.actions)

    @property
    def has_uninstall(self):
        """
        :return: If there are uninstall actions present for the current
        package.
        """
        return K_UNINSTALL_USER_DEFINED in self._data or \
            K_UNINSTALL_GENERATED in self._data

    @require_status(Status.INSTALLED)
    @restore_working_directory
    def execute_uninstall(self, condition_checker):
        if not self.has_uninstall:
            self._status = Status.NOT_INSTALLED
            return

        from dotfiles.stages.uninstall import Uninstall
        executor = Uninstall(self,
                             condition_checker,
                             self._expander)

        # Start the execution in the package resource folder.
        self._load_resources()
        os.chdir(self.resource_dir)

        for step in (self._data.get(K_UNINSTALL_USER_DEFINED, []) +
                     self._data.get(K_UNINSTALL_GENERATED, [])):
            if not executor(**step):
                self.set_failed()
                raise ExecutorError(self, K_UNINSTALL_USER_DEFINED, step)

        self._status = Status.NOT_INSTALLED

    def clean_temporaries(self):
        """
        Remove potential TEMPORARY files that were created during install
        from the system.
        """
        success = [f() for f in self._teardown]
        return all(success)

    def __str__(self):
        return self.name


class _PackageTree:
    """Represents the logical tree of package names in an internal data
    structure."""
    def __init__(self):
        self._dict = dict()

    def get_tree(self, name):
        """Return the dict of packages that are subpackages of the specified
        name.
        """
        # A namespace package is a package name that doesn't contain any
        # installation, only provides a logical directory name for packages.
        can_be_namespace = True

        work_dict = self._dict  # Start from the top.
        for part in name.split('.'):
            sub_dict = work_dict.get(part, dict())
            if not sub_dict:
                work_dict[part] = sub_dict
            work_dict = sub_dict

            if work_dict.get("__SELF__"):
                # The current package we are walking is not a namespace
                # anymore.
                can_be_namespace = False

        return work_dict, can_be_namespace

    @property
    def packages(self):
        """Generates the list of registered packages."""
        keys_to_visit = list(self._dict.keys())
        while keys_to_visit:
            key = keys_to_visit.pop(0)
            dict_for_key, _ = self.get_tree(key)
            for subkey in dict_for_key.keys():
                if subkey == "__SELF__" and dict_for_key[subkey]:
                    yield key
                if isinstance(dict_for_key[subkey], dict):
                    keys_to_visit.append(key + '.' + subkey)

    def is_name(self, name):
        """Returns whether the package tree with the given name was
        encountered, i.e. it exists as a "directory" in the logical structure.
        """
        dict_for_name, _ = self.get_tree(name)
        # The name has been encountered if it has at least a child, and thus
        # the dict is not empty.
        return bool(dict_for_name)

    def is_registered(self, name):
        """Returns whether the given name represent a package."""
        dict_for_name, is_namespace = self.get_tree(name)
        return not is_namespace and dict_for_name["__SELF__"]

    def has_any_non_namespace_parents(self, name):
        """Returns whether the given package name in the current package tree
        has any non-namespace (i.e. actual package) parents.
        """
        name_parts = name.split('.')
        name_prefixes = ['.'.join(name_parts[:num])
                         for num in range(len(name_parts))]
        for prefix in name_prefixes:
            _, can_be_namespace = self.get_tree(prefix)
            if not can_be_namespace:
                return True

        return False

    def register_package(self, name):
        """Add the given package name to the tree."""
        dict_for_package, _ = self.get_tree(name)
        dict_for_package["__SELF__"] = True


def get_package_names(root_map):
    """
    Returns the logical name of packages that are available under the specified
    roots.
    """
    # It has to be ensured that if more roots are loaded, packages under a
    # subsequent root will neither override, nor extend with subpackage the
    # trees found in earlier roots.
    #
    # This dict will save all the packages that have been found during the
    # search.
    package_tree = _PackageTree()

    for root, root_path in root_map.items():
        packages_in_current_root = _PackageTree()

        for dirpath, _, files in os.walk(root_path):
            for match in fnmatch.filter(files, 'package.yaml'):
                logical_package_name = Package.data_file_to_package_name(
                    root_path, os.path.join(dirpath, match))
                if package_tree.has_any_non_namespace_parents(
                            logical_package_name) or \
                        package_tree.is_registered(logical_package_name):
                    # If the to-be-registered package or a parent name has
                    # already been shadowed by a package from a previous
                    # root, do not register it.
                    continue
                packages_in_current_root.register_package(logical_package_name)
                yield logical_package_name

        for package in packages_in_current_root.packages:
            package_tree.register_package(package)


def get_dependencies(package_store, package, ignore=None):
    """
    Calculate the logical names of the packages that are the dependencies of
    the given package instance.
    :param package_store: A dict of package instances that is the memory map of
        known packages.
    :param package: The package instance for whom the dependencies should be
        calculated.
    :param ignore: An optional list of package *NAMES* that should be ignored -
        if these packages are encountered, the dependency chain walk does not
        continue.
    """
    # This recursion isn't the fastest algorithm for creating dependencies,
    # but due to the relatively small size and scope of the project, this
    # will do.
    if ignore is None:
        ignore = []
    if package.name in ignore:
        return []

    dependencies = []
    for dependency in set(package.dependencies) - set(ignore):
        try:
            # Check if the dependency exists.
            dependency_obj = package_store[dependency]
        except KeyError:
            if dependency == package.parent:
                # Don't consider dependency on the parent an error if the
                # parent does not exist as a real package.
                continue

            raise KeyError("Dependency '%s' for '%s' was not found as a "
                           "package."
                           % (dependency, package.name))

        # If the dependency exists as a package, it is a dependency.
        dependencies += [dependency]
        # And walk the dependencies of the now found dependency.
        dependencies.extend(get_dependencies(package_store,
                                             dependency_obj,
                                             ignore + [package.name]))

    return dependencies
