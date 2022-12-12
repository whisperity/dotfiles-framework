class _PackageAction:
    def __init__(self, user_data, package_objects, specified_packages=None):
        self._user_data = user_data
        self._package_objs = package_objects
        self.packages_involved = specified_packages if specified_packages \
            else []

    @property
    def packages(self):
        """
        Returns
        -------
            The list of package names involved in an action.
        """
        return self.packages_involved

    def setup_according_to_dependency_graph(self):
        pass

    def action(self):
        pass
