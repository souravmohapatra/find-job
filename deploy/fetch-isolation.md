# Fetching isolation: rule set for owner review (not installed)

Status: PREPARED, NOT INSTALLED. Section 9 of FINISH_DEVELOPMENT_AND_VALIDATE.md gates
arbitrary-URL fetching on a proven container boundary. Compose `internal: true` removes
the default internet route but does not enforce traffic directionality between
containers. This document is the explicit scoped rule set, installation persistence,
verification and rollback for owner review.

## Current state (already in place)

- `fetcher` container: only the fetcher token secret; no database, CV, OpenRouter,
  Brave or ntfy credentials; no Docker socket; no host network. It serves the
  authenticated fetch RPC on port 8001 (`app/fetcher/main.py`).
- Egress only via Squid (`deploy/squid.conf`): denies non-global IPv4/IPv6
  destinations at connection time, restricts ports to 80/443, allows only GET/HEAD
  CONNECT, no cache, no forwarded headers.
- Fetcher resolves DNS itself and refuses non-global results before connecting
  (`resolve_public`), retries every hop through the proxy, and bounds body size,
  robots, pacing and cooldowns.

## What is missing and why these rules

Docker `internal` networks still allow every container on the same bridge to open
connections to each other and (via the host routing table where present) to LAN and
tailnet addresses. Same-bridge container traffic reaches the host firewall only because
Docker enables `br_netfilter` with `bridge-nf-call-iptables=1`; the installer asserts
that precondition and refuses otherwise. Rules go in `DOCKER-USER` (the chain Docker
guarantees is evaluated before container traffic, survives Docker restarts of other
rulesets) and carry the `jobfinder-fetch-control` comment.

Rule set (`deploy/fetch-control-rules.sh install`; dry read-only: `show`):

1. `fetch_control` bridge: ACCEPT ESTABLISHED,RELATED (worker RPC replies).
2. `fetch` bridge: ACCEPT ESTABLISHED,RELATED (proxy replies).
3. `fetch_control`: DROP NEW connections sourced from the fetcher IP — workers may
   initiate fetch RPCs; the fetcher may not initiate anything.
4. `fetch` bridge: DROP NEW from the proxy IP (the proxy opens nothing).
5. `fetch` bridge: ACCEPT NEW fetcher → proxy:3128 only.
6. `fetch` bridge: DROP any other NEW from the fetcher.
7. Any interface: DROP NEW sourced from the fetcher IP (cross-bridge, LAN, host,
   tailnet egress; rule 5 exempts the proxy port because it is evaluated first).

Worker → fetcher RPC (port 8001) is deliberately NOT listed as an accept: it stays
allowed by falling through `DOCKER-USER` to Docker's own chains, so only the fetcher's
outbound initiation is constrained.

## Installation persistence

Rules live in Docker's chains and are lost on reboot. Persistence is a systemd oneshot
unit (`deploy/jobfinder-fetch-control.service`) that runs `install` after
`docker.service` (idempotent; `verify` fails closed on drift such as recreated
containers with new addresses). Install it only after the rule set passes the real
acceptance matrix.

## Verification plan (section 9.2 matrix)

`scripts/test-fetch-isolation.py` (to be run only with the gate temporarily enabled on
a controlled acceptance instance) proves with disposable listeners and synthetic
payloads: worker→fetcher RPC with the correct token works; wrong/missing token
rejected; public HTTP/HTTPS through the proxy works; direct public IP without proxy
blocked; fetcher-initiated connections to controlled worker/core/host/LAN/tailnet
listeners blocked including same-bridge initiation; proxy denies private IPv4/IPv6,
mapped addresses and non-80/443; redirect-to-private and DNS-rebinding destinations
blocked at connection time; browser containment reuses these controls (section 10);
oversized/decompress-bomb/timeout/redirect-loop produce bounded failures, never a
false empty inventory. Public catalog metadata only; no real metadata services, LAN
applications or private credentials are used as targets.

## Rollback

`deploy/fetch-control-rules.sh rollback` removes exactly the seven marked rules
(newest first) and restores Docker defaults. `show` lists the managed rules at any
time. No generic flush is used anywhere.
