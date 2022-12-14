from collections import deque
import sys

from dotfiles.argument_expander import deduplicate_iterable
from dotfiles.package import get_dependencies, Package
from .package_action import _PackageAction


class Uninstall(_PackageAction):
    def __init__(self, user_data, package_objects, specified_packages):
        super().__init__(user_data, package_objects, specified_packages)

    def setup_according_to_dependency_graph(self):
        """
        Check the dependencies of packages known to be installed and extend
        the removal list with the dependents of the packages the user intended
        to remove, creating a sensible order of removals.
        """
        installed_packages = sorted(list(self._user_data.installed_packages))

        def _create_inverted_dependency_graph():
            ret = dict()

            for name in sorted(list(self._user_data.installed_packages)):
                package = self._package_objs[name]

                # Use the raw key in the data, as we do not want the
                # transitive nature of get_dependencies().
                for dep in package.dependencies:
                    dependees_of_dep = ret.get(dep, list())
                    if not dependees_of_dep:
                        ret[dep] = dependees_of_dep

                    dependees_of_dep.append(name)

            return ret

        forward_deps = _create_inverted_dependency_graph()
        result = list()

        def _walk(package):
            for dependent in forward_deps.get(package.name, list()):
                package2 = self._package_objs[dependent]
                _walk(package2)

                print("%s depends on %s (being uninstalled), will uninstall "
                      "too..." % (package2, package))
                result.append(package2.name)

            result.append(package.name)

        for name in self.packages_involved:
            instance = self._package_objs[name]
            if instance.is_support:
                raise PermissionError("%s is a support package that is not "
                                      "to be directly uninstalled, its life "
                                      "is restricted to helping other "
                                      "packages' installation process!" % name)
            if not instance.is_installed:
                print("%s is not installed -- nothing to uninstall." % name)
                continue

            _walk(instance)

        self.packages_involved = deque(deduplicate_iterable(result))

    def execute(self, is_simulation, user_context, condition_engine,
                transformers):
        """
        Actually perform removal of the packages involved in the action.
        """
        def _uninstall(package):
            if is_simulation:
                print("Remove %s" % package)
                return True

            if not package.has_uninstall:
                # (Uninstall should always be called to advance the status of
                # the package even if it does not do any action.)
                package.execute_uninstall(user_context, condition_engine,
                                          list())
                print("Remove %s: Trivial." % package)
                return True

            try:
                package.execute_uninstall(user_context, condition_engine,
                                          transformers)
                print("Remove %s" % package)
                return True
            except Exception as e:
                print("Fail %s: Remove failed." % package, file=sys.stderr)
                print(e, file=sys.stderr)
                import traceback
                traceback.print_exc()
                return False

        queue = deque(self.packages)
        any_fail = False
        while queue:
            print("------------------=====================-------------------")
            package = self._package_objs[queue.popleft()]
            print("Select %s" % package)

            if not _uninstall(package):
                package.set_failed()
                any_fail = True
                continue

            print("Success %s" % package)
            if not is_simulation and not package.is_support:
                user_context.save_status(package)

        return not any_fail
