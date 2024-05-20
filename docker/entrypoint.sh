#!/bin/sh
set -e

rage_quit() {
	echo "CRITICAL ERROR: $*"
	echo "CRITICAL ERROR: $*" >&2
	exit 1
}

# If we want to generate a token
if [ "$#" -gt 0 ]
then
	if [ "$1" = "sh" ]
	then
		exec /bin/ash
	elif [ "$1" = "python" ]
	then
		exec poetry run python
	fi
fi

# Let's start the serve!
set --

if [ "$VERBOSE" != "" ]
then
    set -- "$@" -v

    if [ "$VERBOSE" -gt 1 ]
    then
        set -- "$@" -v
    fi
    if [ "$VERBOSE" -gt 2 ]
    then
        set -- "$@" -v
    fi
fi

if [ "$REMOTE" = "" ]
then
    rage_quit "To run this in a docker container, you have to provide a remote server."
fi
ping -c 1 "$REMOTE" || rage_quit "Cannot reach the remote SMB server"

if [ "$HOST" = "" ]
then
    rage_quit "To run this in a docker container, you have to provide a remote server."
else
	if [ "X$DO_NOT_VERIFY_REVERSE_PROXY" != "XThe reverse proxy send X-Forwarded-For and X-Forwarded-Host headers" ]
	then
		tmpfile="$(mktemp)"
		printf 'HTTP/1.1 200 OK\n\n\n' | nc -lvp 8080 >"$tmpfile" &
		echo "Testing the reverse proxy"
		curl -k https://"$HOST/$WEBPATH" || rage_quit "We cannot verify the reverse proxy: curl exited with code $?. Quitting"
		grep -q 'X-Forwarded-For:' "$tmpfile" || rage_quit "It seems that the reverse proxy is not proper configured: can't find X-Forwarded-For in the request!"
		grep -q 'X-Forwarded-Host:' "$tmpfile" || rage_quit "It seems that the reverse proxy is not proper configured: can't find X-Forwarded-Host in the request!"
	fi
fi


if [ "X$WEBPATH" != "X" ]
then
	set -- "$@" --webpath "$WEBPATH"
fi

set -- "$@" "$REMOTE" "$HOST"

if [ "$UNSAFE_DEVELOPMENT_MODE" = "This is UNSAFE and I want to make this server more vulnerable, PLease, TrUST me, I reALly reaLLY wanT to Be haCKed!" ]
then
	echo "WARNING! YOU ENABLED THE DEVELOPMENT MODE. THUS, THIS APPLICATION WILL BE MUCH MORE VULNERABLE!"
    set -- "$@" --unsafe-development-mode
	# shellcheck disable=SC2048,SC2086
    exec poetry run python /app/app.py "$@"
fi

exec poetry run gunicorn --preload --reuse-port --group nogroup --proxy-allow-from '*' --bind 0.0.0.0:8080 \
                         --workers 2 "app:create_app('$*')"
