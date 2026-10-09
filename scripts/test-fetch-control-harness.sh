#!/usr/bin/env bash
# Disposable-networks firewall harness for the fetch-control rule set.
#
# Run with root:  sudo scripts/test-fetch-control-harness.sh
#
# It builds a throwaway two-bridge topology mimicking the real stack (worker+fetcher
# on one internal bridge, fetcher+proxy on the other), ESTABLISHES every listener's
# reachability BEFORE any rule exists, then applies the EXACT rule function from
# deploy/fetch-control-rules.sh, re-runs the positives (must stay allowed) and runs
# the negatives (must become blocked). Resources use unique names and are registered
# at creation time; cleanup removes only what this run created, plus its own marked
# rules. No jobfinder bridge, container or rule is touched.

set -u
cd "$(dirname "$0")/.."
MARK="jobfinder-fetch-harness"
JOBFINDER_FC_MARK="$MARK"
# shellcheck source=/dev/null
source deploy/fetch-control-rules.sh

SUF="$$"
NET_FC="h-fc-$SUF"
NET_FETCH="h-fetch-$SUF"
WORKER="h-worker-$SUF"
FETCHER="h-fetcher-$SUF"
PROXY="h-proxy-$SUF"
HOST_PORT=$((18000 + SUF % 1000))
FAILURES=0
CONTAINERS=()
NETWORKS=()
PIDS=()
CLEANED=0

cleanup() {
	local resource pid
	[ "$CLEANED" -eq 1 ] && return
	CLEANED=1
	remove_rules >/dev/null 2>&1
	for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null; done
	for resource in "${CONTAINERS[@]}"; do docker rm -f "$resource" >/dev/null 2>&1; done
	for resource in "${NETWORKS[@]}"; do docker network rm "$resource" >/dev/null 2>&1; done
}
trap cleanup EXIT

check() { # name, expected(allowed|blocked), command...
	local name=$1 expected=$2
	shift 2
	if "$@" >/dev/null 2>&1; then outcome=allowed; else outcome=blocked; fi
	if [ "$outcome" = "$expected" ]; then
		echo "PASS: $name ($outcome as expected)"
	else
		echo "FAIL: $name (got $outcome, expected $expected)"
		FAILURES=$((FAILURES + 1))
	fi
}

must_allow() { # reachability preconditions: identical probe, must succeed
	local name=$1
	shift
	if "$@" >/dev/null 2>&1; then
		echo "reachable: $name"
	else
		die "listener unreachable before any rule was applied: $name (topology broken)"
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
NETWORKS+=("$NET_FC")
docker network create --internal "$NET_FETCH" >/dev/null || die "cannot create $NET_FETCH"
NETWORKS+=("$NET_FETCH")
docker run -d --name "$WORKER" --network "$NET_FC" alpine:latest sleep 300 >/dev/null ||
	die "worker container failed"
CONTAINERS+=("$WORKER")
docker run -d --name "$FETCHER" --network "$NET_FC" alpine:latest sleep 300 >/dev/null ||
	die "fetcher container failed"
CONTAINERS+=("$FETCHER")
docker network connect "$NET_FETCH" "$FETCHER" >/dev/null
docker run -d --name "$PROXY" --network "$NET_FETCH" alpine:latest sleep 300 >/dev/null ||
	die "proxy container failed"
CONTAINERS+=("$PROXY")

fc_bridge=$(printf 'br-%.12s' "$(docker network inspect "$NET_FC" --format '{{.Id}}')")
fetch_bridge=$(printf 'br-%.12s' "$(docker network inspect "$NET_FETCH" --format '{{.Id}}')")
fetcher_fc=$(docker inspect "$FETCHER" --format \
	"{{range \$name, \$net := .NetworkSettings.Networks}}{{if eq \$name \"$NET_FC\"}}{{\$net.IPAddress}}{{end}}{{end}}")
fetcher_fetch=$(docker inspect "$FETCHER" --format \
	"{{range \$name, \$net := .NetworkSettings.Networks}}{{if eq \$name \"$NET_FETCH\"}}{{\$net.IPAddress}}{{end}}{{end}}")
worker_ip=$(docker inspect "$WORKER" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | awk '{print $1}')
proxy=$(docker inspect "$PROXY" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | awk '{print $1}')
gateway=$(docker network inspect "$NET_FC" --format '{{(index .IPAM.Config 0).Gateway}}')
[ -n "$fetcher_fc" ] && [ -n "$fetcher_fetch" ] && [ -n "$proxy" ] && [ -n "$gateway" ] &&
	[ -n "$worker_ip" ] || die "topology addresses unresolved"

start_listener "$FETCHER" 8001
start_listener "$WORKER" 8002
start_listener "$PROXY" 3128
# A persistent host listener behind the bridge gateway (netcat-openbsd -k): a one-shot
# listener would die on the baseline probe and the post-rule negative would pass
# trivially on a closed port instead of proving INPUT enforcement.
nc -lk "$HOST_PORT" >/dev/null 2>&1 &
HOST_LISTENER=$!
PIDS+=("$HOST_LISTENER")
sleep 1

# Establish EVERY listener BEFORE rules exist; a failure here is topology, not policy.
# The two negatives are baselined too: they must be reachable first, so a later
# block proves the firewall did it.
must_allow "worker→fetcher 8001" docker exec "$WORKER" nc -z -w2 "$fetcher_fc" 8001
must_allow "fetcher→worker 8002" docker exec "$FETCHER" nc -z -w2 "$worker_ip" 8002
must_allow "fetcher→proxy 3128" docker exec "$FETCHER" nc -z -w2 "$proxy" 3128
must_allow "proxy→fetcher 8001" docker exec "$PROXY" nc -z -w2 "$fetcher_fetch" 8001
must_allow "fetcher→host listener $HOST_PORT" docker exec "$FETCHER" nc -z -w2 "$gateway" "$HOST_PORT"
kill -0 "$HOST_LISTENER" || die "host listener died during baseline"

apply_rules "$fc_bridge" "$fetch_bridge" "$fetcher_fc" "$fetcher_fetch" "$proxy" ||
	{ remove_rules; die "apply_rules failed; harness rules removed"; }

# Positives must survive the rules.
check "worker→fetcher RPC (same bridge, worker-initiated)" allowed \
	docker exec "$WORKER" nc -z -w2 "$fetcher_fc" 8001
check "fetcher→proxy port (the only allowed outbound)" allowed \
	docker exec "$FETCHER" nc -z -w2 "$proxy" 3128
check "fetcher DNS via Docker embedded resolver" allowed \
	docker exec "$FETCHER" nslookup example.com
# Negatives must now be blocked, including same-bridge initiation and host INPUT.
check "fetcher→worker (same bridge, fetcher-initiated)" blocked \
	docker exec "$FETCHER" nc -z -w2 "$worker_ip" 8002
check "proxy→fetcher (proxy-initiated)" blocked \
	docker exec "$PROXY" nc -z -w2 "$fetcher_fetch" 8001
check "fetcher→host gateway listener (INPUT coverage)" blocked \
	docker exec "$FETCHER" nc -z -w2 "$gateway" "$HOST_PORT"
# The negative results are meaningful only if the listeners outlived the probes.
kill -0 "$HOST_LISTENER" || die "host listener died during probes; INPUT result is not evidence"
start_listener "$WORKER" 8002 # busybox nc loops, but re-assert liveness for the record

echo
if [ "$FAILURES" -eq 0 ]; then
	echo "HARNESS PASSED: all boundaries behaved as designed on disposable networks."
else
	echo "HARNESS FAILED: $FAILURES unexpected result(s). Do NOT install on the real stack."
	exit 1
fi
