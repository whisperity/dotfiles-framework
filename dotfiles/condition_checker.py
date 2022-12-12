from enum import Enum
import subprocess
import sys


class SuperuserCondition:
    IDENTIFIER = "superuser"
    DESCRIPTION = "Superuser (root, sudo) access grants permissions to " \
                  "change system-wide configuration. This might be " \
                  "**DANGEROUS** when granted for packages obtained from " \
                  "an unknown source!"

    def check(self):
        """
        Checks for superuser permission.
        """
        print("Testing access to the 'sudo' command, please enter your "
              "password as prompted.",
              file=sys.stderr)
        print("If you don't have superuser access, please press Ctrl-D.",
              file=sys.stderr)

        try:
            res = subprocess.check_call(
                ['sudo', '-p', "[sudo] password for user '%p' for Dotfiles: ",
                 'echo', "sudo check successful."])
            return not res
        except Exception as e:
            print("Checking 'sudo' access failed! Assuming no 'sudo'.",
                  file=sys.stderr)
            print(str(e), file=sys.stderr)
            return False


class Conditions(Enum):
    SUPERUSER = SuperuserCondition


class ConditionStore:
    """
    Stores the results for conditions that had been checked, and allows an
    action to verify that the conditions are as expected.
    """

    def __init__(self):
        self._values = {cond: None for cond in Conditions}

    def update(self, condition, value):
        """
        Stores the `value` for the `condition` in the saved state.
        """
        if condition not in Conditions:
            raise ValueError("Invalid condition '%s' updating the state."
                             % str(condition))
        if type(value) is not bool:
            raise TypeError("Conditions should be binary.")

        self._values[condition] = value
        return value

    def check_and_store_if_new(self, condition):
        """
        If `condition` has not been evaluated and cached yet, execute the check
        and cache the result.

        Returns
        -------
            The result (either the cached, or the immediately evaluted).
        """
        if condition not in Conditions:
            raise ValueError("Invalid condition '%s' updating the state."
                             % str(condition))
        if self._values[condition] is None:
            self._values[condition] = condition.value().check()
        return self._values[condition]

    def __call__(self, condition_list):
        """
        Returns whether all the conditions in `condition_list` are known to be
        satisfied.
        """
        if not condition_list:
            return True

        return all([v
                    for k, v
                    in self._values.items()
                    if k in condition_list
                    and v is True])
