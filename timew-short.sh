#!/bin/bash

active=$(timew get dom.active)
# Get active tracking info
if [[ "$active" == "1" ]]; then
  main_tag=$(timew get dom.active.tag.1)
  secondary_tag=$(timew get dom.active.tag.2)
  [ "$secondary_tag" == "DOM reference 'dom.active.tag.55' is not valid." ] && secondary_tag=""
  duration=$(timew get dom.active.duration | perl -pe 's/^PT//; s/(\d+)S$//';)
else
  main_tag=""
  duration=""
fi

if [[ "$1" == "start" ]]; then
    # Start a new activity
    if [[ "$main_tag" == RETAGME-* ]]
    then
	number=$(echo $main_tag | cut -f1 -d-)
	number=$((number+1))
	timew start RETAGME-$number
    else
	timew start RETAGME-0
    fi
    exit
fi


if [[ "$active" == "1" ]]; then
  echo "⏱️ $main_tag $secondary_tag | $duration"
else
  echo "No active tracking"
fi


