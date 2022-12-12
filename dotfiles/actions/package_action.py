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

    @property
    def package_objects(self):
        """
        Returns
        -------
            Generates `.Package` objects for the packages that are marked as
            "involved".
        """
        for name in self.packages:
            yield self._package_objs[name]

    def uninvolve(self, package_name):
        """
        Removes the given named package from the list of packages in the
        action.
        """
        self.packages_involved.remove(package_name)

    def setup_according_to_dependency_graph(self):
        pass

    def execute(self, user_context, condition_engine):
        pass
