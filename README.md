`.`-files
=========

> **Note:** This repository contains the management code for installing
> packages, and not the actual "dotfiles" themselves.
> See [Dotfiles](http://github.com/whisperity/Dotfiles).

Synopsis
--------

**dotfiles** repositories are commonly used for synchronising files related to
\*nix shell environments.
In addition to offering a synchronisation source, this piece of software also
helps set up some more sought utilities and tools.

```bash
usage: dotfiles [-h] [-l | -i | -u] [package [package ...]]
```


Usage
-----

The `dotfiles.py` main script handles installing the environment.
Specify the packages to install.

If no packages are specified, the list and description of packages will be
shown.
If package names are specified, the default action is to **install** the
packages.

Listing status for a particular package is possible if `--list` is explicitly
specified: `dotfiles --list foo bar`.


:warning: **Note:** This tool is intended to be used when a new user
profile is created, such as when a new machine is installed.



### Package globber

Multiple packages belonging to a package "group" can be selected by saying
`group.*` or `group.__ALL__`.



### Package sources

Multiple package sources can be given to Dotfiles.
To edit the package configuration, use the built-in editor by calling

```bash
dotfiles --edit-sources
```

which will allow you to manually add, remove, move the sources.

The package sources are forming a priority list.
When installing a package `foo`, it will be installed from the first source it
is found.


#### Default sources

By default, the manager framework will use the following _2_ package sources,
in order:

 1. Your `~/Dotfiles/packages/` directory.
 2. The author's own [Dotfiles](http://github.com/whisperity/Dotfiles)
    repository.



### Uninstalling packages
To uninstall packages, specify `--uninstall` before the package names:

```bash
dotfiles --uninstall foo
```


Package description details
---------------------------

Packages are present across a number of source root directories, where an
arbitrary hierarchy can be present.

A package is any directory which contains a (valid) `package.json` file.
Subpackages are translated from filesystem hierarchy to logical hierarchy via
`.`, i.e. `tools/system/package.json` denotes the `tools.system` package.

Package descriptor files are [YAML](http://yaml.org)s which contain the
directives describing installation and handling of the package.
Any other file is disregarded by the tool unless explicitly used, e.g. being
the source of a copy operation.

The user-specific package source root configuration is parsed and expanded
at the start of the invocation into special directories under `~/.cache` and
`~/.local/share`.
When a package name `foo` is requested, every package source is queried in the
order configured, until one source is found, or it is realised the package
does not exist.
This resolution order is true for every package name lookup, so it applies to
dependency queries, too.




### Configuration directives

#### `description` (string)

Contains a free form textual description for the package which is printed in
the "help" when `dotfiles.py` is invoked without any arguments.

#### `dependencies` (list of other package names)

The _logical_ names of packages which must be installed before the installation
of the current package could begin.

#### `depend on parent` (boolean, default: `true`)

Whether the package should implicitly depend on the parent (e.g. for
`tools.system`, parent is `tools`), assuming the parent is a valid package.

#### `superuser` (boolean, default: `false`)

Whether installing the package **requires** _superuser_ privileges.
If `true`, the installer will ask for `sudo` in advance, and if the user fails
to authenticate against `sudo`, the package will not be installed.

> **Note:** This is different from the _optional_ superuser privilege request
> that is a condition of a single command performed during package handling.

#### `support` (boolean, default: `false`)

_Support_ packages are packages which have all the necessary directives to
perform an installation, but are **NOT** meant to do persistent changes to the
user's environment and files.

Support packages can be depended upon, but may not be directly installed by
the user.
A support package's "installed" status will not be saved.
Support packages may not have _`uninstall`_ actions.

Packages with `internal` in their name (such as `internal.mypkg`) will
automatically be considered as _support packages_.



### Action directives

The installation of a package consists of two separate phases.
Before the installation of the first package, a **temporary** `$SESSION_DIR` is
created where temporary resources may be shared between packages.
This directory is deleted at the end of execution of all installs.
The usage of this feature is discouraged unless absolutely necessary.

Action directives are laid out in the package descriptor YAML file as
shown below.
Each phase has a **list** of key-value tuples, which will be executed _in the
order_ they are added.
Each tuple must have an **`action`** argument which defines the type/kind of
the action to run.

Action directives may specify a list of conditions, with the `if` and `if not`
keys.
The conditions in the `if` list (positive conditions) must **all** be satisfied,
and none of the conditions in the `if not` (negative conditions) list may be
satisfied for the action to execute.
If the conditions aren't as described for the action, the action will be
skipped, but the rest of the actions will be executed.

The rest of the arguments to specify are specific to the _`action`_ type.


```yaml
prepare:
    - action: shell
      command: echo "True"
```



#### Action conditions (`if` and `if not`)

Every action might take the `if` and `if not` key, which is a list of strings,
each specifying a condition. (See the table below for the options.)

`if` and `if not` can be specified on the same action.
If neither is specified, the action is not conditional, and will always
execute.

```yaml
    - action: print
      if:
        - superuser
      text: "I have sudo!"
    - action: print
      if not:
        - superuser
      text: "I do not have sudo!"
    - action: print
      if:
        - superuser
      if not:
        - superuser
      text: "Impossible to execute... hopefully."
```

|  Condition  | Semantics                                                                                                                                                                                |
|:-----------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `superuser` | Turns one action into a conditional action which is only executed if the user presents `sudo` rights. Note that this is different than setting `superuser: true` for the package itself. |



#### `prepare` (optional)

First, the package's configuration and external dependencies are obtained.
This is called the _preparation phase_.

At the beginning of this phase, the executing environment switches into a
temporary directory.
In most directives, `$TEMPORARY_DIR` can be used to refer to this directory
when specifying a path.


|   Action        | Arguments                    | Semantics                                                                                                    | Failure condition                                     |
|:---------------:|------------------------------|:-------------------------------------------------------------------------------------------------------------|:------------------------------------------------------|
| `copy resource` | `path` (string)              | Copy the file or directory from the package's resources (where `package.yaml` is) to the temporary directory | `path` is invalid or OS-level permission error occurs |
| `git clone`     | `repository` (URL string)    | Obtain a clone of the repository by calling `git`                                                            | `git clone` process fails                             |
| `print`         | `text` (string)              | Emit the message `text` to the user on the standard output.                                                  |                                                       |
| `shell`         | `command` (string)           | Execute `command` in a shell                                                                                 | Non-zero return                                       |
| `shell all`     | `commands` (list of strings) | Execute every command in order                                                                               | At least one command returns non-zero                 |
| `shell any`     | `commands` (list of strings) | Execute the commands in order until one succeeds                                                             | None of the commands returns zero                     |



#### `install`

The installation starts from the `packages/foo/bar/` directory (for package
`foo.bar`).
This phase is the _main_ phase where changes to the user's files should be
done.

In most directives, `$TEMPORARY_DIR` can be used to refer to the _`prepare`_
phase's directory when specifying a path.
(This may only be done if there was a _`prepare`_ phase for the package!)

`$PACKAGE_DIR` refers to the directory where the package's metadata file
(`package.yaml`) and additional resources are.


|   Action           | Arguments                                                                                              | Semantics                                                                                                                                             | Failure condition                                     |
|:------------------:|--------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------|
| `copy`             | `file` (string), `to` (string)                                                                         | Copies `file` to the `to` path                                                                                                                        | OS-level error,                                       |
| `copy`             | `files` (list of string), `to` (string), `prefix` (string, default: empty)                             | As if `copy` was done for all element of `files`, `to` must be the destination directory, optionally prepending `prefix` to each destination filename | OS-level error, `to` isn't an existing directory      |
| `copy tree`        | `dir` (string), `to` (string)                                                                          | Copies the contents of `dir` to the `to` directory, `to` is created by this call                                                                      | OS-level error, `to` is  an existing directory        |
| `make dirs`        | `dirs` (list of strings)                                                                               | Creates the directories specified, and their parents if they don't exist                                                                              | OS-level error happens at creating a directory        |
| `replace`          | `at` (string), `with file` (string), `with files` (list of strings), `prefix` (string, default: empty) | Does the same as `copy` but also prepares restoring (at uninstall) the original target files if they existed                                          | _see failure conditions for `copy`_                   |
| `print`            | `text` (string)                                                                                        | Emit the message `text` to the user on the standard output.                                                                                           |                                                       |
| `shell`            | `command` (string)                                                                                     | Execute `command` in a shell                                                                                                                          | Non-zero return                                       |
| `shell all`        | `commands` (list of strings)                                                                           | Execute every command in order                                                                                                                        | At least one command returns non-zero                 |
| `shell any`        | `commands` (list of strings)                                                                           | Execute the commands in order until one succeeds                                                                                                      | None of the commands returns zero                     |



#### `uninstall`

Uninstall starts from the directory that corresponds to `$PACKAGE_DIR`, but
contains the files that were present in this directory at installation, not
what are *currently* present on the system.
This means that the state of `package.yaml` and the resource files are kept
intact even if the `packages/` directory on the system is updated.

In `uninstall` mode, `$PACKAGE_DIR` refers to this archived directory.

:warning: **Note!** The "original" `$PACKAGE_DIR` is **not accessible** during
_`uninstall`_.


|   Action           | Arguments                                                                                              | Semantics                                                                                                                                             | Failure condition                                   |
|:------------------:|--------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------|
| `remove`           | `file` (string)                                                                                        | Removes the specified `file` if it exists, `file` must be an absolute path                                                                            | OS-level error happens at removal                   |
| `remove`           | `files` (list of strings)                                                                              | Removes all files specified, all files must be specified as an absolute path                                                                          | OS-level error happens at removal                   |
| `remove`           | `where` (strings), `file` or `files` as above                                                          | As above, but `file` or `files` may be a relative path, understood relative to `where`, `where` must be an existing directory's absolute path         | OS-level error, `where` isn't an existing directory |
| `remove dirs`      | `dirs` (list of strings)                                                                               | Removes the specified directory, if it is empty                                                                                                       | OS-level error happens at removing a directory      |
| `remove tree`      | `dir` (string)                                                                                         | Removes the tree (all subdirectories and files) under `dir`                                                                                           | OS-level error, `dir` isn't an existing directory   |
| `restore`          | `file` (string)                                                                                        | Restores the version of the `file` (which must be an absolute path) that was present when the package was installed, if such version exists           | OS-level error                                      |
| `restore`          | `files` (list of strings)                                                                              | Calls `restore` for each file in `files`                                                                                                              | OS-level error                                      |
| `print`            | `text` (string)                                                                                        | Emit the message `text` to the user on the standard output.                                                                                           |                                                     |
| `shell`            | `command` (string)                                                                                     | Execute `command` in a shell                                                                                                                          | Non-zero return                                     |
| `shell all`        | `commands` (list of strings)                                                                           | Execute every command in order                                                                                                                        | At least one command returns non-zero               |
| `shell any`        | `commands` (list of strings)                                                                           | Execute the commands in order until one succeeds                                                                                                      | None of the commands returns zero                   |



##### Automatic `uninstall` actions for `install` directives

Certain _`install`_ directives can automatically be mapped to _`uninstall`_
actions.
At the uninstall of a package, the corresponding actions are executed in
**reverse order** (compared to the order of `install` directives).

If automatic uninstall actions were generated for a package's install, they
are executed **after** the manually written _`uninstall`_ directives are
executed.


| `install` action     | `uninstall` action  | Comment                                                                                                                                                                |
|:--------------------:|:-------------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `copy`               | `remove`            | `file` and `files` are translated in a reasonable manner, `where` is not filled automatically, paths containing environment variables are kept as such for uninstall!  |
| `copy tree(dir, to)` | `remove tree(to)`   |                                                                                                                                                                        |
| `make dirs(dirs)`    | `remove dirs(dirs)` |                                                                                                                                                                        |
| `replace`            | `restore`           | `with file` and `with files` are translated in a reasonable manner, `at` is ignored as paths are translated into absolute paths but retain environment variables       |
