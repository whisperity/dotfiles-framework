from collections import deque

from dotfiles.argument_expander import deduplicate_iterable
from dotfiles.package import get_dependencies
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
