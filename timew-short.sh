#!/bin/bash

active=$(timew get dom.active)
all_tags=$(timew get dom.active.tags)
# Get active tracking info
if [[ "$active" == "1" ]]; then
  main_tag=$(timew get dom.active.tags.1)
  secondary_tag=$(timew get dom.active.tags.2)
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
	css_class=$(echo $all_tags | perl -ne '/\"(~css_class:\w+)\"/ && print $1')
	if [ -n "$css_class" ];
	then
	    timew untag $css_class
	else
	    timew start RETAGME-0
	fi
    fi
    exit
fi

if [[ "$1" == "waybar" ]]
then
    css_class=$(echo $all_tags | perl -ne '/\"~css_class:(\w+)\"/ && print $1')
    all_tags=$(echo "$all_tags" | sed 's/"//g')
    [ -n "$css_class" ] && css_class=', "class": "'"${css_class}\""
    if [[ "$active" == "1" ]]; then
	echo "{ \"text\": \"⏱️ $main_tag $secondary_tag | $duration\" $css_class , \"tooltip\": \"$all_tags\" }"
    else
	echo '{ "text": "No active tracking" }'
    fi
    exit 0
fi

if [[ "$active" == "1" ]]; then
  echo "⏱️ $main_tag $secondary_tag | $duration"
else
  echo "No active tracking"
fi


