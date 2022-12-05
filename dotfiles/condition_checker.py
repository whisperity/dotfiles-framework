# class SuperuserCondition:
#     IDENTIFIER = "superuser"
#
#     def __init__(self,

class ConditionChecker:
    """
    Implements a stateful logic that allows package scripts to store results
    of queries about system conditions.
    """

    def __init__(self):
        self._superuser_access = False

    def set_superuser_allowed(self):
        """Register that the client has superuser access."""
        self._superuser_access = True

    def __call__(self, package_instance, condition_list):
        """Check the condition list given against the stored state."""
        if not condition_list:
            return True

        retval = True  # Assume conditions will match.
        if "superuser" in condition_list:
            retval = retval and self._superuser_access

        return retval
