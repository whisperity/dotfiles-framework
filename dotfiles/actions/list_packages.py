import textwrap
from dotfiles.compatibility.tabulate import tabulate


def action(packages, user_filter=None):
    """
    Performs listing the package details from the `p` package dict.
    """
    if not user_filter:
        # If the user did not filter the packages to list, list everything.
        user_filter = packages.keys()

    headers = ["Source", "Package", "Description"]
    table = []
    for package_name in sorted(user_filter):
        try:
            instance = packages[package_name]
        except KeyError:
            table.append(["???", package_name,
                          "ERROR: This package doesn't exist!"])
            continue

        if instance.is_support:
            continue

        source = "INSTALLED" if instance.is_installed else instance.root

        # Make sure the description isn't too long.
        description = instance.description if instance.description else ''
        description = textwrap.fill(description, width=40)

        table.append([source, instance.name, description])

    print(tabulate(table, headers=headers, tablefmt='fancy_grid'))
