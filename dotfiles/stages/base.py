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
            raise ValueError("Invalid action '%s' requested: do not try "
                             "accessing execution engine internals!"
                             % action)

        action = action.replace(' ', '_')
        try:
            func = getattr(self, action)
        except AttributeError:
            raise ValueError("Invalid action '%s' for package stage '%s'!"
                             % (action, type(self).__name__))

        args = {k.replace(' ', '_')
                # Need to replace "from" because it is a keyword...
                .replace("from", "from_"): v
                for k, v in kwargs.items()}

        # Check the conditions that might apply for the action.
        if "if" in args or "if_not" in args:
            if not self.callback:
                raise NotImplementedError(
                    "Conditional execution specified for action, without "
                    "state callback!")
            if "if" in args:
                if not self.callback(args["if"]):
                    # Positive conditions did not match, skip the action.
                    return True
            if "if_not" in args:
                if self.callback(args["if_not"]):
                    # Negative conditions matched, skip the action.
                    return True

            # Remove these conditional keys because the actual dispatched
            # functions do not understand their meaning.
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
        print("MESSAGE FROM '%s/%s':\n\t%s"
              % (self.package.name, type(self).__name__, text))
