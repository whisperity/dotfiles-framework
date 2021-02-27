from abc import ABCMeta, abstractmethod
import os


from dotfiles import yaml
from dotfiles.os import umask


class Option:
    """Helper class that allows dynamically reading and generating help for
    an option of a source list element.
    """

    def __init__(self, name, prompt, parserFn=None, default=None):
        self.name = name
        self.prompt = prompt
        self.parserFn = parserFn if parserFn else lambda x: x
        self.default = default

    def __call__(self):
        return self.parserFn(input('\t' + self.prompt + ' '))


class SourceListEntry(metaclass=ABCMeta):
    options = [Option("name",
                      "Logical name for the package source?")]

    def __init__(self, type_key, name):
        self.type_key = type_key
        self.name = name


class LocalSourceEntry(SourceListEntry):
    type_key = "local"
    help = "Use a directory somewhere on the local machine as a package source"
    options = [SourceListEntry.options[0],
               Option("directory", "The directory to mirror?")
               ]

    def __init__(self, name, directory):
        super().__init__(LocalSourceEntry.type_key, name)
        self.directory = directory

    def __str__(self):
        return "Local directory '%s'" % self.directory


SUPPORTED_ENTRIES = [LocalSourceEntry]


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
                yield LocalSourceEntry(entry["name"], entry["directory"])

    def add_source(self, entry):
        """Adds a configuration element to the list."""
        if list(filter(lambda e: e["name"] == entry["name"], self.list)):
            raise KeyError("A source entry with name '%s' already exists!"
                           % entry["name"])

        self.list.append(entry)

    def delete_source(self, name):
        try:
            element = list(filter(lambda e: e["name"] == name, self.list))[0]
        except IndexError:
            raise KeyError("A source entry with name '%s' doesn't exist!"
                           % name)

        self.list.remove(element)


@umask(0o077)
def get_sourcelist_file():
    config_root = os.environ.get("XDG_CONFIG_HOME",
                                 os.path.join(os.path.expanduser('~'),
                                              ".config"))
    config_dir = os.path.join(config_root, "Dotfiles")
    os.makedirs(config_dir, exist_ok=True)

    return os.path.join(config_dir, "sources.yaml")
