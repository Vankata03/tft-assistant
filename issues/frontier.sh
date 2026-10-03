#!/usr/bin/env bash
# Print the wayfinder frontier: open, unassigned, unblocked child tickets.
cd "$(dirname "$0")" || exit 1

field() { sed -n "s/^$2:[[:space:]]*//p" "$1" | head -n1; }

declare -A status
for f in [0-9]*.md; do
  status[$(field "$f" id)]=$(field "$f" status)
done

for f in [0-9]*.md; do
  [ "$(field "$f" status)" = open ] || continue
  [ -n "$(field "$f" parent)" ] || continue
  [ -z "$(field "$f" assignee)" ] || continue
  blocked=no
  for b in $(field "$f" blocked_by | tr -d '[],'); do
    [ "${status[$b]}" = closed ] || blocked=yes
  done
  if [ $blocked = no ]; then echo "$f  $(field "$f" labels)  $(field "$f" title)"; fi
done
