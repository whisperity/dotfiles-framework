from collections import deque
import sys

from dotfiles.argument_expander import deduplicate_iterable
from dotfiles.package import get_dependencies, Package
from .package_action import _PackageAction


class Install(_PackageAction):
    def __init__(self, user_data, package_objects, specified_packages):
        super().__init__(user_data, package_objects, specified_packages)

    def setup_according_to_dependency_graph(self):
        """
        Check the dependencies of the packages the user wanted to install and
        extend the install list with the unmet dependencies, creating a
        sensible order of package installations.
        """
        installed_packages = list(self._user_data.installed_packages)

        for name in list(self.packages_involved):
            instance = self._package_objs[name]
            if instance.is_support:
                raise PermissionError("%s is a support package that is not "
                                      "to be directly installed, its life is "
                                      "restricted to helping other packages' "
                                      "installation process!" % name)
            if instance.is_installed:
                print("%s is already installed -- skipping." % name)
                self.packages_involved.remove(name)
                continue

            unmet_dependencies = get_dependencies(
                self._package_objs, instance, installed_packages)
            if unmet_dependencies:
                print("%s needs dependencies to be installed: %s"
                      % (name, ', '.join(unmet_dependencies)))
                self.packages_involved.extendleft(unmet_dependencies)

        self.packages_involved = deque(
            deduplicate_iterable(self.packages_involved))

    def execute(self, is_simulation, user_context, condition_engine,
                transformers):
        """
        Actually perform preparation and installation of the packages involved
        in the action.
        """
        def _check_dependencies(package):
            for dependency_name in package.dependencies:
                try:
                    dependency = self._package_objs[dependency_name]
                    if dependency.is_failed:
                        print("Reject %s: dependency %s Failed"
                              % (package, dependency),
                              file=sys.stderr)
                        return False
                except KeyError:
                    # The dependency found by the name isn't a real package.
                    # This is safe to ignore because the action pre-handled
                    # all dependencies. Usually this happens when the parent
                    # is just a name, not a real package.
                    # print("WARNING: %s is supposed to depend on %s, but "
                    #       "it cannot be found?"
                    #       % (package, dependency_name),
                    #       file=sys.stderr)
                    pass
            return True

        def _prepare(package):
            if is_simulation:
                print("Prepare %s" % package)
                return True

            if not package.has_prepare:
                # (Prepare should always be called to advance the status of
                # the package even if it does not do any action.)
                package.execute_prepare(condition_engine, list())
                return True

            try:
                package.execute_prepare(condition_engine, transformers)
                print("Prepare %s" % package)
                return True
            except Exception as e:
                print("Fail %s: Prepare failed." % package, file=sys.stderr)
                print(e, file=sys.stderr)
                import traceback
                traceback.print_exc()
                return False

        def _install(package):
            if is_simulation:
                print("Install %s" % package)
                return True

            try:
                package.execute_install(condition_engine, transformers)

                # Save the package's metadata and the current state of its
                # resource files into the user's backup archive.
                with user_context.get_package_archive(package.name) as zipf:
                    Package.save_to_archive(package, zipf)

                print("Install %s" % package)
                return True
            except Exception as e:
                print("Fail %s: Install failed." % package, file=sys.stderr)
                print(e, file=sys.stderr)
                import traceback
                traceback.print_exc()
                return False

        queue = deque(self.packages)
        any_fail = False
        while queue:
            print("------------------=====================-------------------")
            package = self._package_objs[queue.popleft()]
            if not _check_dependencies(package):
                package.set_failed()
                any_fail = True
                continue

            print("Select %s" % package)
            package.select()

            if not _prepare(package):
                package.set_failed()
                any_fail = True
                continue

            if not _install(package):
                package.set_failed()
                any_fail = True
                continue

            print("Success %s" % package)
            if not is_simulation and not package.is_support:
                user_context.save_status(package)

        return not any_fail
