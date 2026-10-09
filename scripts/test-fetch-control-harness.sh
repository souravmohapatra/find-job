#!/usr/bin/env bash
# Disposable-networks firewall harness for the fetch-control rule set.
#
# Run with root:  sudo scripts/test-fetch-control-harness.sh
#
# It builds a throwaway two-bridge topology mimicking the real stack (worker+fetcher
# on one internal bridge, fetcher+proxy on the other), applies the EXACT rule function
# from deploy/fetch-control-rules.sh against it, probes every required boundary with
# busybox nc, verifies DNS still resolves through Docker's embedded resolver, and
# cleans up everything (containers, networks, marked rules) on exit — success or not.
# No rule is installed on the jobfinder bridges and no jobfinder container is touched.

set -u
cd "$(dirname "$0")/.."
MARK="jobfinder-fetch-harness"
# Override the shared rule module's marker before sourcing it.
JOBFINDER_FC_MARK="$MARK"
# shellcheck source=/dev/null
source deploy/fetch-control-rules.sh

NET_FC=harness-fc
NET_FETCH=harness-fetch
FAILURES=0
CONTAINERS=()
PIDS=()
CLEANED=0

cleanup() {
	local container pid
	[ "$CLEANED" -eq 1 ] && return
	CLEANED=1
	remove_rules >/dev/null 2>&1
	for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null; done
	for container in "${CONTAINERS[@]}"; do
		docker rm -f "$container" >/dev/null 2>&1
	done
	docker network rm "$NET_FC" "$NET_FETCH" >/dev/null 2>&1
}
trap cleanup EXIT

check() { # name, expected(allowed|blocked), command...
	local name=$1 expected=$2
	shift 2
	if "$@" >/dev/null 2>&1; then
		local outcome=allowed
	else
		local outcome=blocked
	fi
	if [ "$outcome" = "$expected" ]; then
		echo "PASS: $name ($outcome as expected)"
	else
		echo "FAIL: $name (got $outcome, expected $expected)"
		FAILURES=$((FAILURES + 1))
	fi
}

start_listener() { # container, port — busybox nc accepts one connection; loop it
	docker exec -d "$1" sh -c "while true; do nc -l -p $2; done"
}

command -v iptables >/dev/null || die "missing iptables"
[ "$(id -u)" -eq 0 ] || die "run with sudo: iptables and the host listener need root"
for tool in docker nc; do need "$tool"; done
[ "$(rule_counts)" = "0 0" ] || die "jobfinder rules are currently installed; rerun after rollback"

docker network create --internal "$NET_FC" >/dev/null || die "cannot create $NET_FC"
docker network create --internal "$NET_FETCH" >/dev/null || die "cannot create $NET_FETCH"
docker run -d --name harness-worker --network "$NET_FC" alpine:latest sleep 300 >/dev/null || die "worker container failed"
docker run -d --name harness-fetcher --network "$NET_FC" alpine:latest sleep 300 >/dev/null || die "fetcher container failed"
docker network connect "$NET_FETCH" harness-fetcher >/dev/null
docker run -d --name harness-proxy --network "$NET_FETCH" alpine:latest sleep 300 >/dev/null || die "proxy container failed"
CONTAINERS=(harness-worker harness-fetcher harness-proxy)

fc_bridge=$(printf 'br-%.12s' "$(docker network inspect "$NET_FC" --format '{{.Id}}')")
fetch_bridge=$(printf 'br-%.12s' "$(docker network inspect "$NET_FETCH" --format '{{.Id}}')")
fetcher_fc=$(docker inspect harness-fetcher --format \
	"{{range \$name, \$net := .NetworkSettings.Networks}}{{if eq \$name \"$NET_FC\"}}{{\$net.IPAddress}}{{end}}{{end}}")
fetcher_fetch=$(docker inspect harness-fetcher --format \
	"{{range \$name, \$net := .NetworkSettings.Networks}}{{if eq \$name \"$NET_FETCH\"}}{{\$net.IPAddress}}{{end}}{{end}}")
proxy=$(docker inspect harness-proxy --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | awk '{print $1}')
gateway=$(docker network inspect "$NET_FC" --format '{{(index .IPAM.Config 0).Gateway}}')
[ -n "$fetcher_fc" ] && [ -n "$fetcher_fetch" ] && [ -n "$proxy" ] && [ -n "$gateway" ] ||
	die "topology addresses unresolved"

apply_rules "$fc_bridge" "$fetch_bridge" "$fetcher_fc" "$fetcher_fetch" "$proxy" ||
	{ remove_rules; die "apply_rules failed; harness rules removed"; }

start_listener harness-fetcher 8001
start_listener harness-worker 8002
start_listener harness-proxy 3128
# A real host listener behind the bridge gateway: without it, the INPUT probe could
# pass trivially on connection-refused instead of proving the firewall drop.
nc -l 18099 >/dev/null 2>&1 &
HOST_LISTENER=$!
PIDS+=("$HOST_LISTENER")
sleep 1

check "worker→fetcher RPC (same bridge, worker-initiated)" allowed \
	docker exec harness-worker nc -z -w2 "$fetcher_fc" 8001
check "fetcher→worker (same bridge, fetcher-initiated)" blocked \
	docker exec harness-fetcher nc -z -w2 "$(docker inspect harness-worker --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | awk '{print $1}')" 8002
check "fetcher→proxy port (the only allowed outbound)" allowed \
	docker exec harness-fetcher nc -z -w2 "$proxy" 3128
check "proxy→fetcher (proxy-initiated)" blocked \
	docker exec harness-proxy nc -z -w2 "$fetcher_fetch" 8001
check "fetcher→host gateway listener (INPUT coverage)" blocked \
	docker exec harness-fetcher nc -z -w2 "$gateway" 18099
check "fetcher DNS via Docker embedded resolver" allowed \
	docker exec harness-fetcher nslookup example.com

echo
if [ "$FAILURES" -eq 0 ]; then
	echo "HARNESS PASSED: all boundaries behaved as designed on disposable networks."
else
	echo "HARNESS FAILED: $FAILURES unexpected result(s). Do NOT install on the real stack."
	exit 1
fi
