#!/bin/bash
# Puts the eval's made-up profile where the screen skill looks for one.
set -e
mkdir -p "$HOME/.config/upwork-skills"
cp "$(dirname "$0")/../test-profile.md" "$HOME/.config/upwork-skills/profile.md"
