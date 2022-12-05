from collections import deque

from dotfiles.argument_expander import deduplicate_iterable
from dotfiles.package import get_dependencies
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
        for name in list(self.packages_involved):
            instance = self._package_objs[name]
            if instance.is_support:
                raise PermissionError("%s is a support package that is not "
                                      "to be directly removed, its life is "
                                      "restricted to helping other packages' "
                                      "installation process!" % name)
            if not instance.is_installed:
                print("%s is not installed -- nothing to uninstall." % name)
                self.packages_involved.remove(name)
                continue

        # TODO: Perhaps at install save what a package depended on so this
        # does not need to be manually calculated for each installed package.
        removal_set = set(self.packages_involved)
        for name in self._user_data.installed_packages:
            instance = self._package_objs[name]
            dependencies_marked_for_removal = set(
                get_dependencies(self._package_objs, instance)).\
                intersection(removal_set)
            if dependencies_marked_for_removal:
                print("%s has dependencies to be uninstalled: %s"
                      % (name, ', '.join(
                          sorted(dependencies_marked_for_removal))))

                removal_set.add(name)
                self.packages_involved.appendleft(name)

        self.packages_involved = deque(
            deduplicate_iterable(self.packages_involved))
