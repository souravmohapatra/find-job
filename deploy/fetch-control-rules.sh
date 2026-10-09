#!/usr/bin/env bash
# Stateful fetch-control directionality rules for the jobfinder Docker bridges.
#
# NOT INSTALLED BY DEFAULT. Section 9 of FINISH_DEVELOPMENT_AND_VALIDATE.md requires
# owner review of this exact rule set before installation. Compose `internal: true`
# only removes the default internet route; it does not restrict same-bridge or
# cross-bridge container traffic. These rules add the missing directionality:
#
#   - workers may open connections to the fetcher's RPC port; replies flow back
#   - the fetcher may open connections ONLY to the egress proxy port
#   - the fetcher and the proxy may not open connections to worker/backend
#     addresses, other bridges, the host LAN, or the tailnet
#
# Same-bridge traffic reaches these rules only because Docker enables
# br_netfilter with bridge-nf-call-iptables=1; the verify command below asserts
# that on this host. Rules are installed in DOCKER-USER (the sanctioned hook that
# Docker guarantees is evaluated before container traffic) and carry the
# "jobfinder-fetch-control" comment for exact-match removal on rollback.
#
# Usage:
#   fetch-control-rules.sh install     # idempotent; refuses on unexpected state
#   fetch-control-rules.sh verify      # assert rules present and host preconditions
#   fetch-control-rules.sh rollback    # remove exactly the marked rules
#   fetch-control-rules.sh show        # print the managed rules

set -u
cd "$(dirname "$0")/.." # repo root: docker compose reads compose.yaml from here
MARK="jobfinder-fetch-control"
COMPOSE_PROJECT="jobfinder"
# Ports the fetcher may CONTACT: egress proxy only.
FETCHER_ALLOWED_PORT="3128"
# Port workers may CONTACT on the fetcher.
FETCHER_RPC_PORT="8001"

die() { echo "BLOCKED: $*" >&2; exit 2; }
need() { command -v "$1" >/dev/null || die "missing tool: $1"; }
need iptables; need docker; need awk

network_bridge() { # compose network name -> host bridge interface
	local name network_id
	name="${COMPOSE_PROJECT}_$1"
	network_id=$(docker network inspect "$name" --format '{{.Id}}' 2>/dev/null) ||
		die "network $name not found; is the compose stack up?"
	printf 'br-%.12s' "$network_id"
}

container_ip() { # compose service -> IPv4 on its named network
	local container
	container=$(docker compose -p "$COMPOSE_PROJECT" ps -q "$1" 2>/dev/null) ||
		die "cannot query service $1"
	[ -n "$container" ] || die "service $1 is not running"
	docker inspect "$container" --format \
		"{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}" | awk '{print $1}'
}

fetcher_ip() { container_ip fetcher; }
proxy_ip() { container_ip egress-proxy; }

assert_preconditions() {
	docker network inspect "${COMPOSE_PROJECT}_fetch_control" --format '{{json .Internal}}' |
		grep -q true || die "fetch_control must be an internal network"
	docker network inspect "${COMPOSE_PROJECT}_fetch" --format '{{json .Internal}}' |
		grep -q true || die "fetch must be an internal network"
	# Same-bridge traffic must traverse iptables for these rules to bind.
	[ "$(cat /proc/sys/net/bridge/bridge-nf-call-iptables 2>/dev/null)" = "1" ] ||
		die "bridge-nf-call-iptables is not 1; same-bridge traffic would bypass these rules"
	iptables -L DOCKER-USER >/dev/null 2>&1 ||
		die "DOCKER-USER chain missing; Docker firewall management is unavailable"
}

rule() { # print the managed rule for the given arguments
	iptables -S DOCKER-USER | grep -- "$MARK"
}

install() {
	assert_preconditions
	local fc_bridge fetch_bridge fetcher proxy
	fc_bridge=$(network_bridge fetch_control)
	fetch_bridge=$(network_bridge fetch)
	fetcher=$(fetcher_ip)
	proxy=$(proxy_ip)
	[ -n "$fetcher" ] && [ -n "$proxy" ] || die "fetcher/proxy addresses unresolved"

	# Idempotency: refuse when unexpected managed rules exist from a different
	# topology; a previous identical install is a no-op.
	if iptables -S DOCKER-USER | grep -q -- "$MARK"; then
		echo "managed rules already present; verifying instead"
		verify
		return
	fi

	# 1) Replies for established flows in both directions, on both bridges.
	iptables -I DOCKER-USER 1 -i "$fc_bridge" -o "$fc_bridge" \
		-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT -m comment --comment "$MARK"
	iptables -I DOCKER-USER 2 -i "$fetch_bridge" -o "$fetch_bridge" \
		-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT -m comment --comment "$MARK"

	# 2) fetch_control: drop NEW connections INITIATED BY the fetcher (source
	#    fetcher IP). Worker-initiated RPC to the fetcher stays allowed; the reply
	#    is covered by the established rule above.
	iptables -I DOCKER-USER 3 -i "$fc_bridge" -o "$fc_bridge" -s "$fetcher" \
		-m conntrack --ctstate NEW -j DROP -m comment --comment "$MARK"

	# 3) fetch bridge: the fetcher may open only the proxy port; the proxy may
	#    open nothing. Worker backend networks are unreachable from this bridge
	#    (internal, no gateway), and these rules hold even if that changes.
	iptables -I DOCKER-USER 4 -i "$fetch_bridge" -o "$fetch_bridge" -s "$proxy" \
		-m conntrack --ctstate NEW -j DROP -m comment --comment "$MARK"
	iptables -I DOCKER-USER 5 -i "$fetch_bridge" -o "$fetch_bridge" -s "$fetcher" \
		-d "$proxy" --dport "$FETCHER_ALLOWED_PORT" -m conntrack --ctstate NEW \
		-j ACCEPT -m comment --comment "$MARK"
	iptables -I DOCKER-USER 6 -i "$fetch_bridge" -o "$fetch_bridge" -s "$fetcher" \
		-m conntrack --ctstate NEW -j DROP -m comment --comment "$MARK"

	# 4) Cross-bridge and routed egress from the fetcher (LAN, host, tailnet):
	#    drop NEW in either direction through any other interface, in addition to
	#    Docker's absent default route on internal networks.
	iptables -I DOCKER-USER 7 -s "$fetcher" -m conntrack --ctstate NEW \
		-j DROP -m comment --comment "$MARK"

	echo "installed. Rules survive only until the next boot or Docker restart;"
	echo "install the fetch-control-rules systemd unit for persistence (see"
	echo "deploy/fetch-isolation.md) and run: fetch-control-rules.sh verify"
}

verify() {
	assert_preconditions
	local count
	count=$(iptables -S DOCKER-USER | grep -c -- "$MARK")
	[ "$count" -eq 7 ] || die "expected 7 managed rules, found $count; run rollback and reinstall"
	# Container addresses must still match the rules; a recreated container moves.
	local fetcher proxy
	fetcher=$(fetcher_ip)
	proxy=$(proxy_ip)
	iptables -S DOCKER-USER | grep -q -- "-s $fetcher " ||
		die "fetcher address changed since install; rollback and reinstall"
	iptables -S DOCKER-USER | grep -q -- "-s $proxy " ||
		die "proxy address changed since install; rollback and reinstall"
	echo "verified: 7 managed rules present and bound to current addresses"
}

rollback() {
	local rule
	# Delete ONLY rules carrying the marker, newest first for stable indices.
	while read -r rule; do
		[ -n "$rule" ] || continue
		rule=${rule#-A DOCKER-USER }
		iptables -D DOCKER-USER $rule || die "failed to remove rule: $rule"
	done < <(iptables -S DOCKER-USER | grep -- "$MARK" | tac)
	echo "rolled back: managed rules removed; Docker defaults restored"
}

show() {
	iptables -S DOCKER-USER | grep -- "$MARK" || echo "no managed rules present"
}

case "${1:-}" in
install) install ;;
verify) verify ;;
rollback) rollback ;;
show) show ;;
*) echo "usage: $0 {install|verify|rollback|show}" >&2; exit 2 ;;
esac
