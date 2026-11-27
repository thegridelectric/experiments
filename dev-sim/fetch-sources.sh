#!/usr/bin/env bash
# Make ./.sources/<repo> at the commit sources.txt names, for every line.
#
#     ./fetch-sources.sh
#
# Each is a clone of the sibling checkout of the same name, so nothing is
# fetched from the network and the sibling's branch and working tree are
# left alone. The sibling must already have the commit (git fetch there
# if it does not). A clone already at its commit is left as it is.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$HERE/.sources"
mkdir -p "$SRC"

while read -r repo commit; do
    case "$repo" in ''|'#'*) continue ;; esac
    sibling="$ROOT/$repo"
    dest="$SRC/$repo"
    if [[ ! -d "$sibling/.git" ]]; then
        echo "no sibling checkout $sibling" >&2
        exit 1
    fi
    if ! git -C "$sibling" cat-file -e "$commit^{commit}" 2>/dev/null; then
        echo "$repo: the sibling checkout does not have $commit; git fetch there" >&2
        exit 1
    fi
    if [[ ! -d "$dest/.git" ]]; then
        git clone --quiet --no-checkout "$sibling" "$dest"
    fi
    if [[ "$(git -C "$dest" rev-parse HEAD 2>/dev/null)" == "$commit" ]] \
        && [[ -z "$(git -C "$dest" status --porcelain)" ]]; then
        continue
    fi
    # A clone copies the sibling's branches. A commit only a remote-tracking
    # ref reaches there (origin/main ahead of main) comes with this fetch.
    git -C "$dest" fetch --quiet "$sibling" '+refs/remotes/*:refs/remotes/sibling/*'
    git -C "$dest" checkout --quiet --detach "$commit"
    echo "$repo at ${commit:0:8}"
done < "$HERE/sources.txt"
