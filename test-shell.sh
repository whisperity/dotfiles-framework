#!/bin/bash
# Create a temporary HOME directory and run a shell there to test Dotfiles
# without having to mess up the user's real home.

TEMPHOME=$(mktemp -d)

pushd ${TEMPHOME}
touch .is_dotfiles_temporary_home \
    .sudo_as_admin_successful       # Don't show the Ubuntu default message...

# Set up ~/Dotfiles in the temporary home as a symbolic link to the hardcoded
# automatically used ~/Dotfiles "source repository" of the script.
ln -s $(readlink -f ~/Dotfiles) ./Dotfiles

popd


clear
HOME="${TEMPHOME}" bash

# Cleanup.
rm -rf "${TEMPHOME}"
