#!/usr/bin/env bash
# Stateful fetch-control directionality rules for the jobfinder Docker bridges.
#
# NOT INSTALLED BY DEFAULT. Section 9 of FINISH_DEVELOPMENT_AND_VALIDATE.md requires
# owner review, and the corrected rule set must pass the disposable-network harness
# (scripts/test-fetch-control-harness.sh) before installation on the real stack.
#
# What these rules enforce (Compose `internal: true` does NOT):
#   - workers may open connections to the fetcher's RPC port; replies flow back
#   - the fetcher may open connections ONLY to the egress proxy port
#   - fetcher/proxy may not open connections to worker/backend addresses, other
#     bridges, the host (INPUT), the LAN or the tailnet
#
# Chain coverage: DOCKER-USER sees FORWARD traffic (cross-bridge and, through
# Docker's br_netfilter hook, same-bridge). Container→HOST traffic traverses INPUT,
# which DOCKER-USER never sees, so the fetcher addresses also get explicit INPUT
# drops. Rules carry the "jobfinder-fetch-control" comment for exact-match removal.
#
# Usage:
#   fetch-control-rules.sh install     # transactional; auto-rollback on error
#   fetch-control-rules.sh verify      # assert rules present, addresses current
#   fetch-control-rules.sh rollback    # remove exactly the marked rules
#   fetch-control-rules.sh show        # print the managed rules
#
# The harness sources this file and calls apply_rules/remove_rules against a
# disposable topology; the rule shapes are shared, never duplicated.

set -u
cd "$(dirname "$0")/.." # repo root: docker compose reads compose.yaml from here
# The harness overrides MARK so its disposable rules can never collide with (or be
# removed by) the real stack's rollback.
MARK="${MARK:-jobfinder-fetch-control}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-jobfinder}"
FETCHER_ALLOWED_PORT="${FETCHER_ALLOWED_PORT:-3128}"

die() { echo "BLOCKED: $*" >&2; exit 2; }
need() { command -v "$1" >/dev/null || die "missing tool: $1"; }

network_bridge() { # compose network name -> host bridge interface
	local network_id
	network_id=$(docker network inspect "${COMPOSE_PROJECT}_$1" --format '{{.Id}}' 2>/dev/null) ||
		die "network ${COMPOSE_PROJECT}_$1 not found; is the compose stack up?"
	printf 'br-%.12s' "$network_id"
}

address_on() { # compose service, compose network -> IPv4 on that network
	local container
	container=$(docker compose -p "$COMPOSE_PROJECT" ps -q "$1" 2>/dev/null) ||
		die "cannot query service $1"
	[ -n "$container" ] || die "service $1 is not running"
	docker inspect "$container" --format \
		"{{range \$name, \$net := .NetworkSettings.Networks}}{{if eq \$name \"${COMPOSE_PROJECT}_$2\"}}{{\$net.IPAddress}}{{end}}{{end}}"
}

assert_preconditions() {
	docker network inspect "${COMPOSE_PROJECT}_fetch_control" --format '{{json .Internal}}' |
		grep -q true || die "fetch_control must be an internal network"
	docker network inspect "${COMPOSE_PROJECT}_fetch" --format '{{json .Internal}}' |
		grep -q true || die "fetch must be an internal network"
	# Same-bridge traffic reaches the rules only through Docker's netfilter hook.
	[ "$(cat /proc/sys/net/bridge/bridge-nf-call-iptables 2>/dev/null)" = "1" ] ||
		die "bridge-nf-call-iptables is not 1; same-bridge traffic would bypass these rules"
	iptables -L DOCKER-USER >/dev/null 2>&1 || die "cannot read DOCKER-USER (root required)"
}

# apply_rules <fc_bridge> <fetch_bridge> <fetcher_fc_ip> <fetcher_fetch_ip> <proxy_ip>
# Every rule is marked; any failure returns nonzero so install can roll back.
apply_rules() {
	local fc_bridge=$1 fetch_bridge=$2 fetcher_fc=$3 fetcher_fetch=$4 proxy=$5
	local rule
	# Replies for established flows, both bridges.
	iptables -I DOCKER-USER 1 -i "$fc_bridge" -o "$fc_bridge" \
		-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT -m comment --comment "$MARK" || return 1
	iptables -I DOCKER-USER 2 -i "$fetch_bridge" -o "$fetch_bridge" \
		-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT -m comment --comment "$MARK" || return 1
	# fetch_control: the fetcher initiates nothing toward worker addresses.
	iptables -I DOCKER-USER 3 -i "$fc_bridge" -o "$fc_bridge" -s "$fetcher_fc" \
		-m conntrack --ctstate NEW -j DROP -m comment --comment "$MARK" || return 1
	# fetch bridge: the proxy initiates nothing.
	iptables -I DOCKER-USER 4 -i "$fetch_bridge" -o "$fetch_bridge" -s "$proxy" \
		-m conntrack --ctstate NEW -j DROP -m comment --comment "$MARK" || return 1
	# fetch bridge: the fetcher's ONLY permitted outbound initiation.
	iptables -I DOCKER-USER 5 -i "$fetch_bridge" -o "$fetch_bridge" -s "$fetcher_fetch" \
		-d "$proxy" -p tcp --dport "$FETCHER_ALLOWED_PORT" -m conntrack --ctstate NEW \
		-j ACCEPT -m comment --comment "$MARK" || return 1
	iptables -I DOCKER-USER 6 -i "$fetch_bridge" -o "$fetch_bridge" -s "$fetcher_fetch" \
		-m conntrack --ctstate NEW -j DROP -m comment --comment "$MARK" || return 1
	# Cross-bridge and routed egress from either fetcher address (LAN, tailnet).
	iptables -I DOCKER-USER 7 -s "$fetcher_fc" -m conntrack --ctstate NEW \
		-j DROP -m comment --comment "$MARK" || return 1
	iptables -I DOCKER-USER 8 -s "$fetcher_fetch" -m conntrack --ctstate NEW \
		-j DROP -m comment --comment "$MARK" || return 1
	# Container→host traffic bypasses FORWARD entirely: cover INPUT explicitly.
	iptables -I INPUT 1 -s "$fetcher_fc" -m conntrack --ctstate NEW \
		-j DROP -m comment --comment "$MARK" || return 1
	iptables -I INPUT 2 -s "$fetcher_fetch" -m conntrack --ctstate NEW \
		-j DROP -m comment --comment "$MARK" || return 1
}

# remove_rules: delete exactly the marked rules, newest first, both chains.
remove_rules() {
	local rule
	while read -r rule; do
		[ -n "$rule" ] || continue
		rule=${rule#-A DOCKER-USER }
		iptables -D DOCKER-USER $rule || die "failed to remove DOCKER-USER rule: $rule"
	done < <(iptables -S DOCKER-USER | grep -- "$MARK" | tac)
	while read -r rule; do
		[ -n "$rule" ] || continue
		rule=${rule#-A INPUT }
		iptables -D INPUT $rule || die "failed to remove INPUT rule: $rule"
	done < <(iptables -S INPUT | grep -- "$MARK" | tac)
}

rule_counts() {
	echo "$(iptables -S DOCKER-USER | grep -c -- "$MARK") $(iptables -S INPUT | grep -c -- "$MARK")"
}

install() {
	need docker
	assert_preconditions
	if [ "$(rule_counts)" != "8 2" ]; then
		[ "$(rule_counts)" = "0 0" ] || die "unexpected existing managed rules; run rollback first"
	fi
	local fc_bridge fetch_bridge fetcher_fc fetcher_fetch proxy
	fc_bridge=$(network_bridge fetch_control) || return 1
	fetch_bridge=$(network_bridge fetch) || return 1
	fetcher_fc=$(address_on fetcher fetch_control) || return 1
	fetcher_fetch=$(address_on fetcher fetch) || return 1
	proxy=$(address_on egress-proxy fetch) || return 1
	[ -n "$fetcher_fc" ] && [ -n "$fetcher_fetch" ] && [ -n "$proxy" ] ||
		die "fetcher/proxy addresses unresolved on the expected networks"

	# Transactional: any failure rolls the partial policy back before exiting.
	if ! apply_rules "$fc_bridge" "$fetch_bridge" "$fetcher_fc" "$fetcher_fetch" "$proxy"; then
		remove_rules
		die "rule installation failed; partial rules were rolled back"
	fi
	verify
	echo "installed. Rules are lost on reboot; install the persistence unit"
	echo "(deploy/jobfinder-fetch-control.service) only after the acceptance matrix passes."
}

verify() {
	assert_preconditions
	[ "$(rule_counts)" = "8 2" ] || die "expected 8 DOCKER-USER and 2 INPUT managed rules, found $(rule_counts)"
	local fetcher_fc fetcher_fetch proxy
	fetcher_fc=$(address_on fetcher fetch_control) || return 1
	fetcher_fetch=$(address_on fetcher fetch) || return 1
	proxy=$(address_on egress-proxy fetch) || return 1
	iptables -S DOCKER-USER | grep -q -- "-s $fetcher_fc " || die "fetcher control address changed; rollback and reinstall"
	iptables -S DOCKER-USER | grep -q -- "-s $fetcher_fetch " || die "fetcher egress address changed; rollback and reinstall"
	iptables -S DOCKER-USER | grep -q -- "-s $proxy " || die "proxy address changed; rollback and reinstall"
	echo "verified: rules present and bound to current addresses"
}

rollback() {
	need docker
	remove_rules
	echo "rolled back: managed rules removed; Docker defaults restored"
}

show() {
	echo "DOCKER-USER:"; iptables -S DOCKER-USER | grep -- "$MARK" || echo "  (none)"
	echo "INPUT:"; iptables -S INPUT | grep -- "$MARK" || echo "  (none)"
}

# CLI entry: skipped when the harness sources this file for apply_rules/remove_rules.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
	case "${1:-}" in
	install) install ;;
	verify) verify ;;
	rollback) rollback ;;
	show) show ;;
	*) echo "usage: $0 {install|verify|rollback|show}" >&2; exit 2 ;;
	esac
fi
