#!/bin/bash

# JSON string escaping, for the hand-built waybar output
json_escape() {
    printf '%s' "$1" | perl -0777 -pe 's/(["\\])/\\$1/g; s/\n/\\n/g; s/\t/\\t/g'
}

active=$(timew get dom.active)
all_tags=$(timew get dom.active.tags)
# Get active tracking info
if [[ "$active" == "1" ]]; then
  main_tag=$(timew get dom.active.tags.1)
  # An invalid reference prints its error on stdout, so go by the exit status.
  secondary_tag=$(timew get dom.active.tags.2) || secondary_tag=""
  duration=$(timew get dom.active.duration | perl -pe 's/^PT//; s/(\d+)S$//';)
else
  main_tag=""
  duration=""
fi

if [[ "$1" == "start" ]]; then
    # Start a new activity
    if [[ "$main_tag" == RETAGME-* ]]
    then
	number=$(echo "$main_tag" | cut -f1 -d-)
	number=$((number+1))
	timew start RETAGME-$number
    else
	css_class=$(echo "$all_tags" | perl -ne '/\"(~css_class:\w+)\"/ && print $1')
	if [ -n "$css_class" ];
	then
	    timew untag "$css_class"
	else
	    timew start RETAGME-0
	fi
    fi
    exit
fi

if [[ "$1" == "waybar" ]]
then
    css_class=$(echo "$all_tags" | perl -ne '/\"~css_class:(\w+)\"/ && print $1')
    [ -n "$css_class" ] && css_class=', "class": "'"${css_class}\""
    if [[ "$active" == "1" ]]; then
	text=$(json_escape "⏱️ $main_tag $secondary_tag | $duration")
	# The tags one by one: dom.active.tags quotes and escapes them for the shell.
	tags=()
	for ((i = 1; i <= $(timew get dom.active.tags.count); i++)); do
	    tags+=("$(timew get "dom.active.tags.$i")")
	done
	tooltip=$(json_escape "${tags[*]}")
	echo "{ \"text\": \"$text\" $css_class , \"tooltip\": \"$tooltip\" }"
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


