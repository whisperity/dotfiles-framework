from abc import ABCMeta, abstractmethod
import os
import shutil

from dotfiles import yaml
from dotfiles.os import cache_directory, config_directory, data_directory, \
    umask


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
        self._assembled_at = None
        self.type_key = type_key
        self.name = name

    @abstractmethod
    def assemble(self, data_directory):  # noqa: F811
        """Overridden in the derived classes to execute the action needed in
        setting up the directory structure for the package source.
        """
        pass

    @property
    def location_on_disk(self):
        """Returns the location (after the instance is assemble()d) where the
        contents of the package source can be found.
        """
        if not self._assembled_at:
            raise Exception("Can't know location_on_disk before assemble()!")
        return self._assembled_at


class LocalSourceEntry(SourceListEntry):
    type_key = "local"
    help = "Use a directory somewhere on the local machine as a package source"
    options = [SourceListEntry.options[0],
               Option("directory", "The directory to mirror?",
                      lambda path: os.path.abspath(os.path.expanduser(path)))
               ]

    def __init__(self, name, directory):
        super().__init__(LocalSourceEntry.type_key, name)
        self.directory = directory

    def __str__(self):
        return "Local directory '%s'" % self.directory

    def assemble(self, data_directory):  # noqa: F811
        # Create a symbolic link under the data_directory to the referred
        # directory.
        target_symlink = os.path.join(data_directory, self.name)
        if os.path.exists(target_symlink):
            os.remove(target_symlink)
        os.symlink(self.directory, target_symlink, target_is_directory=True)
        self._assembled_at = target_symlink


SUPPORTED_ENTRIES = [LocalSourceEntry]


class SourceList:
    def __init__(self, path):
        self.path = path
        self._list = list()
        self._entries = list()

    def load(self):
        try:
            with open(self.path, 'r') as listfile:
                data = yaml.load_yaml(listfile, Loader=yaml.Loader)
                self._list = data.get("sources", list())
                self._create_entries()
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
                data = {"sources": self._list}
                yaml.dump_yaml(data, listfile, Dumper=yaml.Dumper)
        except FileNotFoundError:
            raise FileNotFoundError("Failed to save source list '%s'"
                                    % self.path)

    def _create_entries(self):
        """Instantiate the `SourceListEntry` class for the configured sources,
        in order."""
        self._entries = list()

        for entry in self._list:
            print(entry)
            type_key = entry["type"]
            if type_key == "local":
                self._entries.append(LocalSourceEntry(entry["name"],
                                                      entry["directory"]))

    @property
    def sources(self):
        """Return the package sources configured."""
        if not self._entries:
            self._create_entries()

        for entry in self._entries:
            yield entry

    @property
    def num_sources(self):
        return len(self._list)

    def add_source(self, entry):
        if list(filter(lambda e: e["name"] == entry["name"], self._list)):
            raise KeyError("A source entry with name '%s' already exists!"
                           % entry["name"])

        self._list.insert(0, entry)
        self._create_entries()

    def delete_source(self, name):
        try:
            element = list(filter(lambda e: e["name"] == name, self._list))[0]
        except IndexError:
            raise KeyError("A source entry with name '%s' doesn't exist!"
                           % name)

        self._list.remove(element)
        self._create_entries()

    def swap_sources(self, name, direction):
        """Moves the source named 'name' up or down on the priority list.
        Returns True if a move was performed.
        """
        if direction not in ['UP', 'DOWN']:
            raise ValueError("Invalid direction '%s'" % direction)

        try:
            element = list(filter(lambda e: e["name"] == name, self._list))[0]
        except IndexError:
            raise KeyError("A source entry with name '%s' doesn't exist!"
                           % name)

        index = self._list.index(element)
        if direction == 'UP':
            if index == 0:
                return

            previous = self._list[index - 1]
            self._list[index] = previous
            self._list[index - 1] = element
        elif direction == 'DOWN':
            if index == len(self._list) - 1:
                return

            following = self._list[index + 1]
            self._list[index] = following
            self._list[index + 1] = element

        self._create_entries()
        return True

    def _clear_symlinks(self):
        """Clears the priority list's symbolink links from the user's cache."""
        directory = os.path.join(cache_directory(), "sourcelist")
        try:
            shutil.rmtree(directory)
        except Exception:
            pass

    @umask(0o077)
    def _setup_symlinks(self):
        """Creates the symbolic links in the user's cache in order of
        priority."""
        directory = os.path.join(cache_directory(), "sourcelist")
        os.makedirs(directory, exist_ok=True)

        # Calculate how many leading zeroes are to be formatted.
        digits_needed = len(str(len(self._list)))
        format_str = "{:0" + str(digits_needed) + "d}-{}"

        for idx, entry in enumerate(self._entries):
            os.symlink(entry.location_on_disk,
                       os.path.join(directory,
                                    format_str.format(idx, entry.name)),
                       target_is_directory=True)

    def assemble(self):
        """Assembles the package configuration to be used by the installer."""
        if not self._entries:
            self._create_entries()

        self._clear_symlinks()

        directory = os.path.join(data_directory(), "sources.d")
        os.makedirs(directory, exist_ok=True)

        for entry in self._entries:
            entry.assemble(directory)

        self._setup_symlinks()


@umask(0o077)
def get_sourcelist_file():
    os.makedirs(config_directory(), exist_ok=True)
    return os.path.join(config_directory(), "sources.yaml")
