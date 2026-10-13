#!/usr/bin/env bash
# Starts the API and, when LIVEKIT_URL is set, the voice agent in the same container.
# If either process exits, the other is stopped and the container exits with its
# status, so the platform restarts both (never an API running with a dead voice).
set -u

# Empty host = every interface, IPv4 AND IPv6 ("::" would be IPv6-only, "0.0.0.0"
# IPv4-only). Railway's private network (*.railway.internal) needs IPv6.
uvicorn api:app --host "" --port 3002 --proxy-headers &

if [ -n "${LIVEKIT_URL:-}" ]; then
    # Same container: the voice agent reaches the API over loopback.
    export RETHREAD_API_URL="${RETHREAD_API_URL:-http://127.0.0.1:3002}"
    (cd /app/voice && exec .venv/bin/python agent.py start) &
else
    echo "LIVEKIT_URL not set: voice agent disabled, running the API only"
fi

stop() {
    kill -TERM $(jobs -p) 2>/dev/null
    wait
}
trap 'stop; exit 0' TERM INT

wait -n
status=$?
echo "A process exited (status $status); stopping the container"
stop
# Neither process should ever end on its own: even a clean exit (the voice worker
# exits 0 when it fails to start) is a failure, so restart-on-failure kicks in.
exit $(( status == 0 ? 1 : status ))
