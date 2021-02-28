
class _StageBase:
    """
    The base class from which all stage executors inherit from.
    """
    def __init__(self, package, condition_check_callback):
        self.package = package
        self.callback = condition_check_callback

    def __call__(self, action, **kwargs):
        """
        Dynamically dispatch the actual execution of the action.
        """
        if action.startswith('_'):
            raise AttributeError("Invalid action '%s' requested: do not try "
                                 "accessing execution engine internals!"
                                 % action)

        action = action.replace(' ', '_')
        try:
            func = getattr(self, action)
        except AttributeError:
            raise AttributeError("Invalid action '%s' for package stage "
                                 "'%s'!" % (action, type(self).__name__))

        args = {k.replace(' ', '_'): v for k, v in kwargs.items()}

        if "if" in args or "if_not" in args:
            if not self.callback:
                raise TypeError("Conditional execution specified for action, "
                                "without check callback!")
            if "if" in args:
                if not self.callback(self.package, args["if"]):
                    # Positive conditions did not match, skip the action.
                    return True
            if "if_not" in args:
                if self.callback(self.package, args["if_not"]):
                    # Negative conditions matched, skip the action.
                    return True

            # Remove these keys because the actual dispatched functions do not
            # understand their meaning.
            try:
                del args["if"]
            except KeyError:
                pass
            try:
                del args["if_not"]
            except KeyError:
                pass

        ret = func(**args)
        if ret is None:
            # Assume true if the function didn't return anything.
            ret = True
        return ret

    def print(self, text):
        """Print a message to the user."""
        print("MESSAGE FROM '%s':\n\t%s" % (self.package.name, text))
