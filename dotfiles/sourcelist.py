from abc import ABCMeta, abstractmethod
from collections import OrderedDict
import os
import shutil
import subprocess
import sys

from dotfiles import yaml
from dotfiles.os import cache_directory, config_directory, data_directory, \
    restore_working_directory, umask


DEFAULT_SOURCE_LIST = [
    {"type": "local",
     "name": "My-Dotfiles",
     "directory": os.path.join(os.path.expanduser('~'),
                               "Dotfiles",
                               "packages/")
     },
    {"type": "git repo",
     "name": "Whisperity-Dotfiles",
     "repository": "http://github.com/whisperity/Dotfiles.git",
     "refspec": "",
     "directory": "packages/"
     }
]


class Option:
    """Helper class that allows dynamically reading and generating help for
    an option of a source list element.
    """

    def __init__(self, name, prompt, parser_fn=None, default=None):
        self.name = name
        self.prompt = prompt
        self.parser_fn = parser_fn if parser_fn else lambda x: x
        self.default = default

    def __call__(self):
        """Ask the user to specify an option."""
        return self.parser_fn(input('\t' + self.prompt + ' '))

    def from_entry(self, entry):
        """Fetch the value for the option from the given configuration file
        entry.
        """
        if self.default is not None:
            return entry.get(self.name, self.default)
        return entry[self.name]


def _no_special_in_name(name):
    if '/' in name or ' ' in name:
        raise ValueError("Name must not contain a / or Space!")
    return name


class SourceListEntry(metaclass=ABCMeta):
    options = [Option("name",
                      "Logical name for the package source?",
                      _no_special_in_name)]

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


class LocalSource(SourceListEntry):
    type_key = "local"
    help = "Use a directory somewhere on the local machine as a package source"
    options = [SourceListEntry.options[0],
               Option("directory", "The directory to mirror?",
                      lambda path: os.path.abspath(os.path.expanduser(path)))
               ]

    def __init__(self, name, directory):
        super().__init__(LocalSource.type_key, name)
        self.directory = directory

    def __str__(self):
        return "Local directory '%s'" % self.directory

    def assemble(self, data_directory):  # noqa: F811
        # Create a symbolic link under the data_directory to the referred
        # directory.
        target_symlink = os.path.join(data_directory, self.name)
        if os.path.exists(target_symlink):
            try:
                os.remove(target_symlink)
            except IsADirectoryError:
                # The original directory did not exist and an empty one was
                # created.
                os.rmdir(target_symlink)

        if not os.path.isdir(self.directory):
            print("[WARNING] The source directory of '%s', '%s' does not "
                  "exist."
                  % (self.name, self.directory))
            os.makedirs(target_symlink, exist_ok=True)
        else:
            os.symlink(self.directory, target_symlink,
                       target_is_directory=True)
        self._assembled_at = target_symlink


class GitRepositorySource(SourceListEntry):
    type_key = "git repo"
    help = "Fetch the contents of a Git repository from an URL and use it " \
           "as a package source"
    options = [SourceListEntry.options[0],
               Option("repository", "The repository URL to fetch from?"),
               Option("refspec", "The branch name or commit SHA1 to check "
                                 "out and use? "
                                 "(default: use remote default)",
                      default=""),
               Option("directory", "The directory in the repository where "
                                   "packages are located? "
                                   "(default: repo root) ",
                      default="")
               ]

    def __init__(self, name, repository, refspec, directory):
        super().__init__(GitRepositorySource.type_key, name)
        self.repository = repository
        self.refspec = refspec
        self.directory = directory

    def __str__(self):
        ret = "Git %s" % self.repository
        if self.refspec:
            ret += "@%s" % self.refspec
        if self.directory:
            ret += "/%s" % self.directory
        return ret

    @restore_working_directory
    def _setup_git_remote(self):
        os.chdir(self.__directory)
        subprocess.check_call(["git", "init", '.'], stdout=subprocess.DEVNULL)
        try:
            repo_url = subprocess.check_output(["git", "remote", "get-url",
                                                "__dotfiles__repo__"],
                                               stderr=subprocess.DEVNULL)
            repo_url = repo_url.decode()

            if repo_url != self.repository:
                subprocess.check_call(["git", "remote", "set-url",
                                       "__dotfiles__repo__",
                                       self.repository])
        except subprocess.CalledProcessError:
            subprocess.check_call(["git", "remote", "add",
                                   "__dotfiles__repo__",
                                   self.repository])

    def _get_current_git_commit(self):
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                             stderr=subprocess.DEVNULL)
            commit = commit.decode().strip()
            return commit
        except subprocess.CalledProcessError:
            return ""

    def _get_current_git_branch(self):
        try:
            branch = subprocess.check_output(["git", "rev-parse",
                                              "--abbrev-ref", "HEAD"],
                                             stderr=subprocess.DEVNULL)
            branch = branch.decode().strip()
            if branch == "HEAD":
                return ""
            return branch
        except subprocess.CalledProcessError:
            return ""

    def _git_fetch(self):
        print("[DEBUG] Updating remote '%s'..." % self.name, file=sys.stderr)
        subprocess.check_call(["git", "fetch", "--all", "--tags", "--prune"],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)

    def _git_checkout(self):
        if self.refspec:
            subprocess.run(["git", "branch", "-D", self.refspec],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        subprocess.check_call(["git", "checkout",
                               self.refspec if self.refspec else "FETCH_HEAD"],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)

    @restore_working_directory
    def _git_set_to_refspec(self):
        os.chdir(self.__directory)

        if not self.refspec:
            # Always update if the user didn't specify anything to check out.
            self._git_fetch()
            self._git_checkout()
            return

        current_commit = self._get_current_git_commit()
        if current_commit and current_commit.startswith(self.refspec):
            # If the current commit matches the commit specified, no need to
            # update.
            return

        # Otherwise, the refspec is either a commit, or a branch name.
        if self._get_current_git_branch():
            # If the repository is set to track a remote branch, update, and
            # check out.
            self._git_fetch()
            self._git_checkout()
            return

        # Otherwise, the refspec is a commit.
        try:
            self._git_checkout()
        except subprocess.CalledProcessError:
            # The checkout failed.
            self._git_fetch()
            self._git_checkout()

    def assemble(self, data_directory):  # noqa: F811
        # Git repositories might already exist, so to prevent useless
        # downloads by the client, first let us check if the repository exists.
        git_repo_dir = os.path.join(data_directory, self.name)
        if os.path.exists(git_repo_dir) and not os.path.isdir(git_repo_dir):
            os.remove(git_repo_dir)
        os.makedirs(git_repo_dir, exist_ok=True)

        self.__directory = git_repo_dir

        self._setup_git_remote()
        self._git_set_to_refspec()

        if self.directory:
            self.__directory = os.path.join(git_repo_dir, self.directory)
            if not os.path.exists(self.__directory) or \
                    not os.path.isdir(self.__directory):
                raise NotADirectoryError(
                    "No directory '/%s' in repository '%s'"
                    % (self.directory, self.repository))

        self._assembled_at = self.__directory
        del self.__directory


SUPPORTED_ENTRIES = [LocalSource, GitRepositorySource]


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
            self._list = DEFAULT_SOURCE_LIST
            print("[WARNING] No sourcelist configuration file created, "
                  "substituting with defaults...", file=sys.stderr)
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

        def _create(clazz, entry):
            return clazz(*list(map(lambda opt: opt.from_entry(entry),
                                   clazz.options)))

        self._entries = list()

        for entry in self._list:
            type_key = entry["type"]
            if type_key == "local":
                self._entries.append(_create(LocalSource, entry))
            elif type_key == "git repo":
                self._entries.append(_create(GitRepositorySource, entry))

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
            if not os.path.isdir(entry.location_on_disk):
                continue
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

    @property
    def roots(self):
        """Return the configured package roots, in the priority order."""
        directory = os.path.join(cache_directory(), "sourcelist")

        # Calculate how many leading zeroes are to be formatted.
        digits_needed = len(str(len(self._list)))
        format_str = "{:0" + str(digits_needed) + "d}-{}"

        ret = OrderedDict()
        for idx, entry in enumerate(self._list):
            ret[entry["name"]] = os.path.join(
                directory, format_str.format(idx, entry["name"]))

        return ret

    def filter_roots(self, entry):
        """
        Return a data structure just like `roots` does, but containing only
        `entry`.
        """
        roots = self.roots
        if entry is None:
            return roots

        if entry not in self.roots:
            raise KeyError("The specified package source '%s' is not "
                           "configured!" % entry)
        return {entry: roots[entry]}


@umask(0o077)
def get_sourcelist_file():
    os.makedirs(config_directory(), exist_ok=True)
    return os.path.join(config_directory(), "sources.yaml")
