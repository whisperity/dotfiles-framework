import os
import pprint

from dotfiles.stages import Stages


class _Transformer:
    def __init__(self, identifier, enabled, affecting_stages):
        self._identifier = identifier
        self._enabled = enabled
        self._affecting_stages = affecting_stages

    @property
    def identifier(self):
        return self._identifier

    def __str__(self):
        return self.identifier

    @property
    def is_enabled(self):
        return self._enabled

    def transform(self, xform_config, action):
        """Implemented by subclasses to perform the transformation
        unconditionally.
        """
        raise NotImplementedError("Must be implemented in a subclass!")

    @staticmethod
    def _get_configuration(identifier, action_dict):
        """Retrieve the configuration map for the current transformation."""
        meta_root = action_dict.get("$transform", dict())
        cfg = meta_root.get(identifier, None)

        if cfg is None:
            return dict()
        if type(cfg) is dict:
            return cfg
        if type(cfg) is bool:
            return {"enabled": cfg}

        raise TypeError("Expected either a 'bool' for switching transformer, "
                        "or a 'dict' configuration.")

    def _strip_configuration(self, action_dict):
        """
        Strip the configuration map of the current transformation from the
        action object.
        """
        meta_root = action_dict.get("$transform", dict())
        try:
            del meta_root[self.identifier]
        except KeyError:
            pass

    @staticmethod
    def _is_enabled_in(cfg):
        return cfg.get("enabled", True)

    def __call__(self, stage, action_dict):
        """
        Transforms the given action if the current transformer is enabled and
        if the action does not explicitly prohibit the transformation.

        Returns
        -------
            The transformed action.
            It might be a `dict` in which case it is a single transformation,
            or a `list` of `dict`s in which case the action was split into
            multiple transformed actions.
        """
        if stage not in self._affecting_stages:
            return action_dict

        cfg = self._get_configuration(self.identifier, action_dict)
        if not self._is_enabled_in(cfg):
            return action_dict

        result = self.transform(cfg, action_dict)
        if result is not None:
            self._strip_configuration(action_dict)
        else:
            result = action_dict
        return result


class _UltimateTransformer(_Transformer):
    """
    The ultimate transformer which must be executed last in a transformation
    chain. This transformer is **always** enabled, and is responsible for
    cleaning up the 'action' data structure before it is handed over to the
    executors.
    """
    def __init__(self):
        pass

    def __call__(self, stage, action_dict):
        # verify that all the transformations that needed to be run had
        # actually executed.
        meta_root = action_dict.get("$transform", dict())
        if not meta_root:
            return action_dict

        for xformer in list(meta_root.keys()):
            extracted_cfg = \
                _Transformer._get_configuration(xformer, action_dict)

            if _Transformer._is_enabled_in(extracted_cfg) is False:
                # Found a configuration in the transformer meta which points
                # to a disabled transformation. This can be stripped properly.
                del meta_root[xformer]
            else:
                raise NotImplementedError(
                    "Transformer '%s' configuration was given in the "
                    "'package.yaml' file for action '%s' in stage '%s', but "
                    "this transformer was not capable of executing."
                    % (xformer, str(action_dict), str(stage)))

        if not meta_root:
            # The configuration dict properly emptied.
            del action_dict["$transform"]

        return action_dict


def get_ultimate_transformer():
    return _UltimateTransformer()


class CopiesAsSymlinks(_Transformer):
    """
    Transforms a 'copy' or a 'replace' action of an installer into an
    equivalent 'symlink' action with relative path as output, allowing changes
    to a deployed dotfile to be versioned back to the original source
    repository.
    """
    def __init__(self, enabled):
        super().__init__("copies as symlinks", enabled, [Stages.INSTALL])

    @classmethod
    def __handle_copy(cls, action):
        action["action"] = "symlink"
        action["relative"] = True
        return action

    @classmethod
    def __apply_prefix(cls, prefix, path):
        if path is None:
            return None
        if prefix is None:
            return path

        diren, filen = os.path.split(path)
        return os.path.join(diren, prefix + filen)

    @classmethod
    def __handle_replace(cls, action):
        def __clean_dict(mapping):
            return {k: v for k, v in mapping.items() if v is not None}
        # Handling "replace" is harder to make it into a symlink, because the
        # user expects a backup to be available at uninstall.
        remove = __clean_dict(
            {"action": "remove",
             "ignore_missing": True,
             "where": action.get("at", None),
             "file": cls.__apply_prefix(action.get("prefix", None),
                                        action.get("with file", None)),
             "files": list(map(
                 lambda p: cls.__apply_prefix(action.get("prefix", None), p),
                 action.get("with files")))
             if "with files" in action else None
             })

        symlink = __clean_dict(
            {"action": "symlink",
             "relative": True,
             "to": action.get("at", None),
             "file": action.get("with file", None),
             "files": action.get("with files", None),
             "prefix": action.get("prefix", None)
             })

        return [remove, symlink]

    def transform(self, xform_config, action):
        if action["action"] not in ["copy", "replace"]:
            return action

        if "$TEMPORARY_DIR" in pprint.pformat(action):
            # Do not do anything with the action if the temporary installer
            # directory is mentioned. It must stay as-is, because the symlink
            # would dangle after the install session.
            return [action]

        if action["action"] == "copy":
            return self.__handle_copy(action)
        if action["action"] == "replace":
            return self.__handle_replace(action)
