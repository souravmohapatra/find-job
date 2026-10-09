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
	local name=$1 expected=$2 output status outcome
	shift 2
	output=$("$@" 2>&1)
	status=$?
	if [ "$status" -eq 0 ]; then
		outcome=allowed
	elif [ "$status" -eq 1 ] || [ "$status" -eq 124 ]; then
		outcome=blocked
	else
		echo "FAIL: $name (probe execution error, exit $status: $output)" >&2
		FAILURES=$((FAILURES + 1))
		return
	fi
	if [ "$outcome" = "$expected" ]; then
		echo "PASS: $name ($outcome as expected)"
	else
		echo "FAIL: $name (got $outcome, expected $expected; output: $output)" >&2
		FAILURES=$((FAILURES + 1))
	fi
}

must_allow() { # reachability preconditions: identical probe, must succeed
	local name=$1 output status
	shift
	output=$("$@" 2>&1)
	status=$?
	if [ "$status" -eq 0 ]; then
		echo "reachable: $name"
	else
		die "listener unreachable before any rule was applied: $name (exit $status: $output)"
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
must_allow "fetcher internal service-name DNS ($PROXY)" docker exec "$FETCHER" nslookup "$PROXY"
must_allow "worker internal service-name DNS ($FETCHER)" docker exec "$WORKER" nslookup "$FETCHER"
ext_dns_output=$(docker exec "$FETCHER" nslookup example.com 2>&1)
ext_dns_status=$?
if [ "$ext_dns_status" -eq 0 ]; then
	EXT_DNS_BASELINE="allowed"
	echo "baseline: external DNS (example.com) is reachable pre-rules"
else
	EXT_DNS_BASELINE="blocked"
	echo "baseline: external DNS (example.com) is blocked pre-rules (exit $ext_dns_status: $ext_dns_output)"
fi
for c in "${CONTAINERS[@]}"; do
	[ "$(docker inspect -f '{{.State.Running}}' "$c")" = "true" ] || die "container $c died before rules applied"
done

apply_rules "$fc_bridge" "$fetch_bridge" "$fetcher_fc" "$fetcher_fetch" "$proxy" ||
	{ remove_rules; die "apply_rules failed; harness rules removed"; }

# Positives must survive the rules.
check "worker→fetcher RPC (same bridge, worker-initiated)" allowed \
	docker exec "$WORKER" nc -z -w2 "$fetcher_fc" 8001
check "fetcher→proxy port (the only allowed outbound)" allowed \
	docker exec "$FETCHER" nc -z -w2 "$proxy" 3128
check "fetcher internal service-name DNS ($PROXY)" allowed \
	docker exec "$FETCHER" nslookup "$PROXY"
check "worker internal service-name DNS ($FETCHER)" allowed \
	docker exec "$WORKER" nslookup "$FETCHER"
check "fetcher external DNS (matches pre-rule baseline: $EXT_DNS_BASELINE)" "$EXT_DNS_BASELINE" \
	docker exec "$FETCHER" nslookup example.com
# Negatives must now be blocked, including same-bridge initiation and host INPUT.
check "fetcher→worker (same bridge, fetcher-initiated)" blocked \
	docker exec "$FETCHER" nc -z -w2 "$worker_ip" 8002
check "proxy→fetcher (proxy-initiated)" blocked \
	docker exec "$PROXY" nc -z -w2 "$fetcher_fetch" 8001
check "fetcher→host gateway listener (INPUT coverage)" blocked \
	docker exec "$FETCHER" nc -z -w2 "$gateway" "$HOST_PORT"
# The negative results are meaningful only if the listeners and containers outlived the probes.
kill -0 "$HOST_LISTENER" || die "host listener died during probes; INPUT result is not evidence"
for c in "${CONTAINERS[@]}"; do
	[ "$(docker inspect -f '{{.State.Running}}' "$c")" = "true" ] || die "container $c died during probes; negative result is not evidence"
done
echo
if [ "$FAILURES" -eq 0 ]; then
	echo "HARNESS PASSED: all boundaries behaved as designed on disposable networks."
else
	echo "HARNESS FAILED: $FAILURES unexpected result(s). Do NOT install on the real stack."
	exit 1
fi
