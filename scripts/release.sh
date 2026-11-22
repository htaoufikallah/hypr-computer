#!/usr/bin/env bash
# Release a new version: scripts/release.sh patch|minor|major
#   patch: fixes (0.6.0 -> 0.6.1), minor: features (0.6.1 -> 0.7.0), major: breaking changes.
# Bumps .claude-plugin/plugin.json, pushes that commit to main, waits for CI to pass on it,
# then pushes the tag and creates the GitHub Release. Users' `hypr-computer update` installs it.
set -euo pipefail
cd "$(dirname "$0")/.."
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

kind=${1:-}
case "$kind" in patch|minor|major) ;; *) die "usage: scripts/release.sh patch|minor|major" ;; esac
command -v gh >/dev/null || die "needs the GitHub CLI (gh), logged in"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || die "switch to main first"
[ -z "$(git status --porcelain --untracked-files=no)" ] || die "commit or stash your changes first"
git fetch -q origin main --tags
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || die "main is not the same as origin/main; pull or push first"

current=$(python3 -c 'import json; print(json.load(open(".claude-plugin/plugin.json"))["version"])')
IFS=. read -r major minor patch <<<"$current"
case "$kind" in
  patch) next="$major.$minor.$((patch + 1))" ;;
  minor) next="$major.$((minor + 1)).0" ;;
  major) next="$((major + 1)).0.0" ;;
esac
git rev-parse -q --verify "refs/tags/v$next" >/dev/null && die "v$next already exists"
since=$(git describe --tags --abbrev=0 2>/dev/null || true)
echo "Releasing v$next (was v$current). Changes since ${since:-the start}:"
git log --oneline --no-merges ${since:+"$since"..HEAD} | sed 's/^/  /'
printf 'Continue? [y/N] '; read -r ans; [ "$ans" = y ] || die "aborted"

sed -i.bak "s/\"version\": \"$current\"/\"version\": \"$next\"/" .claude-plugin/plugin.json && rm .claude-plugin/plugin.json.bak
git commit -qm "Release v$next" .claude-plugin/plugin.json
git push -q origin main
sha=$(git rev-parse HEAD)

echo "Waiting for CI on ${sha:0:10}..."
run=""
for _ in $(seq 1 60); do
  run=$(gh run list --commit "$sha" --workflow ci --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)
  [ -n "$run" ] && break; sleep 5
done
[ -n "$run" ] || die "CI never started for ${sha:0:10}; v$next was not tagged"
gh run watch "$run" --exit-status >/dev/null || die "CI failed on ${sha:0:10}; v$next was not tagged. Fix it, then run this again."

git tag -a "v$next" -m "v$next"
git push -q origin "v$next"
gh release create "v$next" --verify-tag --latest --title "v$next" --generate-notes ${since:+--notes-start-tag "$since"} >/dev/null
echo "Released v$next: $(gh release view "v$next" --json url --jq .url)"
echo "Users get it with: hypr-computer update"
