from abc import ABCMeta, abstractmethod
import os


from dotfiles import yaml
from dotfiles.os import umask


class OptionHelp:
    """Helper class that allows dynamically reading and generating help for
    an option of a source list element.
    """

    def __init__(self, prompt, parserFn):
        self.prompt = prompt
        self.parserFn = parserFn


class SourceListEntry(metaclass=ABCMeta):
    options = {"logical_name": OptionHelp(
        "Logical name for the package source? ", lambda x: x)
               }

    def __init__(self, type_key, logical_name):
        self.type_key = type_key
        self.name = logical_name


class LocalSourceEntry(SourceListEntry):
    help = "Use a directory somewhere on the local machine as a package source"
    options = {"directory": OptionHelp(
        "The directory to mirror? ", lambda x: x),
               "logical_name": SourceListEntry.options["logical_name"]
               }

    def __init__(self, directory, logical_name):
        super().__init__("local", logical_name)
        self.directory = directory


class SourceList:
    def __init__(self, path):
        self.path = path
        self.list = list()

    def load(self):
        try:
            with open(self.path, 'r') as listfile:
                data = yaml.load_yaml(listfile, Loader=yaml.Loader)
                self.list = data.get("sources", list())
        except FileNotFoundError:
            raise FileNotFoundError("Failed to open source list '%s'"
                                    % self.path)
        except yaml.YAMLError as ye:
            raise ValueError("Source list '%s' has invalid format: %s"
                             % (self.path, str(ye)))

    @umask(0o077)
    def save(self):
        try:
            with open(self.path, 'w') as listfile:
                data = {"sources": self.list}
                yaml.dump_yaml(data, listfile, Dumper=yaml.Dumper)
        except FileNotFoundError:
            raise FileNotFoundError("Failed to save source list '%s'"
                                    % self.path)

    @property
    def sources(self):
        """Instantiate the `SourceListEntry` class for the configured sources,
        in order."""
        for entry in self.list:
            print(entry)
            type_key = entry["type"]
            if type_key == "local":
                yield LocalSourceEntry(entry["directory"], entry["name"])

    def add_source(self, entry, position=None):
        """Adds a configuration element to the list."""
        if list(filter(lambda e: e["name"] == entry["name"], self.list)):
            raise KeyError("A source entry with name '%s' already exists!"
                           % entry["name"])

        if not position:
            self.list.append(entry)
        else:
            self.list.insert(position, entry)


@umask(0o077)
def get_sourcelist_file():
    config_root = os.environ.get("XDG_CONFIG_HOME",
                                 os.path.join(os.path.expanduser('~'),
                                              ".config"))
    config_dir = os.path.join(config_root, "Dotfiles")
    os.makedirs(config_dir, exist_ok=True)

    return os.path.join(config_dir, "sources.yaml")
