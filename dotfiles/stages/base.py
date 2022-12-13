from dotfiles.package import K_CONDITIONAL_POSITIVE, K_CONDITIONAL_NEGATIVE


class _StageBase:
    """
    The base class from which all stage executors inherit from.
    """
    def __init__(self, package, user_context, condition_check_callback):
        self.package = package
        self.user_context = user_context
        self.callback = condition_check_callback

    def __get_action_func(self, action):
        if action.startswith('_'):
            raise ValueError("Invalid action '%s' requested: do not try "
                             "accessing execution engine internals!"
                             % action)

        action = action.replace(' ', '_')
        try:
            return getattr(self, action)
        except AttributeError:
            raise ValueError("Invalid action '%s' for package stage '%s'!"
                             % (action, type(self).__name__))

    @staticmethod
    def __cleanup_args(args):
        return {k.replace(' ', '_')
                # Need to replace "from" because it is a keyword...
                .replace("from", "from_"): v
                for k, v in args.items()}

    @staticmethod
    def __get_meta_key(args, key, default=None):
        return args.get('$' + key.replace(' ', '_'), default)

    @staticmethod
    def __delete_meta_key(args, key):
        try:
            del args['$' + key.replace(' ', '_')]
        except KeyError:
            pass
        return args

    def __evaluate_conditions(self, args):
        # Check the conditions that might apply for the action.
        required_conditions = self.__get_meta_key(
            args, K_CONDITIONAL_POSITIVE, list())
        blocking_conditions = self.__get_meta_key(
            args, K_CONDITIONAL_NEGATIVE, list())
        if required_conditions or blocking_conditions:
            if not self.callback:
                raise NotImplementedError(
                    "Conditional execution specified for action, without "
                    "state callback!")
            if required_conditions and not self.callback(required_conditions):
                # Positive conditions did not match, skip the action.
                return False
            if blocking_conditions and self.callback(blocking_conditions):
                # Negative conditions matched, skip the action.
                return False

        # Remove these conditional keys because the actual dispatched
        # functions do not understand their meaning.
        self.__delete_meta_key(args, K_CONDITIONAL_POSITIVE)
        self.__delete_meta_key(args, K_CONDITIONAL_NEGATIVE)
        return True

    def __call__(self, action, **kwargs):
        """
        Dynamically dispatch the actual execution of the action.
        """
        fn = self.__get_action_func(action)
        args = self.__cleanup_args(kwargs)

        if not self.__evaluate_conditions(args):
            # Skip the action if the conditions did not match.
            return True

        ret = fn(**args)
        # Assume true if the function didn't return anything.
        return ret if ret is not None else True

    def print(self, text):
        """Print a message to the user."""
        print("MESSAGE FROM '%s/%s':\n\t%s"
              % (self.package.name, type(self).__name__, text))
