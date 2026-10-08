# Deployment and operations

Target: Ubuntu Server with Docker Engine and Docker Compose v2, reachable over the local network and local tailnet only. No public ingress, public DNS setup, router forwarding, Tailscale Funnel, or hosted application service is part of this design. Outbound access is needed for public job sites, search, OpenRouter inference, updates, and normal Tailscale connectivity.

## Compose topology

| Service | Role | Persistent data |
| --- | --- | --- |
| edge | Caddy serving built frontend and proxying API/ntfy | Local certificate authority and Caddy state |
| api | FastAPI, owner authentication, job/profile APIs | Private document volume; PostgreSQL |
| worker | Procrastinate control/fetch/notify queues | Document volume; PostgreSQL |
| ai-worker | Procrastinate AI queue | Document volume; PostgreSQL |
| db | PostgreSQL 17 | Database volume |
| fetcher | HTTPX service; Playwright rendering pending | Origin pacing/cooldown state; bounded temporary files |
| egress-proxy | Squid destination filtering for fetcher | No application data |
| ntfy | Private notification server | Auth and message-cache volume |
| migrate | One-shot application and queue migrations | Database |

Use one backend image with separate process commands; fetcher has a browser-enabled image; frontend assets are built into edge with a multi-stage build. Host Tailscale is managed as a normal host service, keeping its privileges out of app containers. There is no local LLM container, model volume, or GPU requirement. AI workers call OpenRouter over outbound HTTPS. An existing local ntfy instance can replace the bundled service through deployment configuration.

Services restart unless stopped, run as non-root where supported, have bounded log rotation, and expose no Docker socket. PostgreSQL, fetcher and backend ports are never published to LAN/tailnet. Health checks and dependency ordering do not replace retry/recovery logic. Migration runs once before starting application workers; it is not launched independently by every replica.

Core, notification, fetch and outbound networks have explicit membership. Only fetcher and proxy share the fetch network; fetcher cannot join core. Proxy is its only outbound path. Worker reaches the fetcher API through a dedicated internal fetch-control network with stateful firewall rules permitting worker-initiated API calls and their responses only; fetcher-initiated connections back to worker addresses are denied. The worker exposes no listener on this network. Verify these rules, including same-bridge traffic, rather than relying on network naming as isolation. Do not accidentally give the fetcher unrestricted core access while wiring control traffic. Arbitrary internet traffic is prohibited from reaching private ranges as described in SOURCES.md.

## LAN and tailnet entry points

Choose two browser origins: app on HTTPS 443; ntfy on HTTPS 8443. LAN hostname example is `jobs.home.arpa`, resolved to the Ubuntu server by local DNS. Actual names/IPs are installation parameters.

Caddy listens for LAN HTTPS on ports bound explicitly to `LAN_IP:443` and `LAN_IP:8443`. It also exposes app and ntfy HTTP listeners on host loopback only at `127.0.0.1:8080` and `127.0.0.1:8081`. Host Tailscale Serve proxies tailnet HTTPS 443 to loopback 8080 and HTTPS 8443 to loopback 8081. Use the device's full tailnet DNS name. No listener binds to all host interfaces; IPv6 stays unpublished until equivalent restrictions are configured.

LAN Caddy sites use `tls internal`, requiring the generated CA root to be trusted on each LAN client. Tailnet clients use Tailscale Serve certificates. Store Caddy CA keys privately and back them up. Explicitly list app LAN/tailnet origins and trusted proxy paths; trust forwarded headers only from known proxy hops. Hostnames do not determine authorization. [Caddy local HTTPS](https://caddyserver.com/docs/automatic-https), [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).

Set the canonical app notification link and ntfy base URL to the tailnet origins for off-LAN use. LAN aliases are additional allowed origins with independent browser sessions. A mobile client must have tailnet connectivity away from home; LAN-only users can choose LAN URLs instead.

Bind published ports explicitly and apply Docker-aware ingress rules permitting only intended LAN and tailnet access. Verify from both allowed and disallowed networks. Do not assume UFW alone filters Docker-published ports; Docker documents that they can bypass its rules. [Docker firewall behaviour](https://docs.docker.com/engine/network/packet-filtering-firewalls/). Do not enable Funnel; it provides public access rather than tailnet-only serving. [Funnel distinction](https://tailscale.com/docs/features/tailscale-funnel).

## Authentication and secrets

One owner account, created by a local bootstrap CLI with an interactive password. No public registration and no first-visitor takeover flow. Use Argon2id password hashing, random opaque sessions stored hashed in PostgreSQL, Secure/HttpOnly/SameSite=Lax cookies, seven-day absolute expiry, logout revocation, CSRF tokens and Origin checks for mutations. Rate-limit login attempts in the database; allow password managers and paste. Credentials remain necessary on the trusted LAN.

Mount deployment secrets as files through Compose secrets: DB password, OpenRouter API key, ntfy publisher token, optional Brave API key, and internal service credentials. Local Compose secret files still need restricted host permissions; they are not an encrypted secret vault. Credentials are never stored in frontend state or returned by settings APIs. Fix the OpenRouter API base URL in deployment configuration; expose task model IDs, routing and budgets as non-secret Settings. Mount the OpenRouter key only into backend processes that need catalog validation or inference. Approved internal ntfy and external OpenRouter traffic are separate from arbitrary source URLs, and credentials must never follow redirects to a different origin.

Keep CVs/private documents off the static web root. Only authenticated download handlers may return them. Job content renders as plain text/structured sections, with safe external links. No third-party analytics or external fonts are loaded by the web client.

## ntfy policy

Set auth default access to deny-all. Give the app a publish-only token for its topic and the owner a read credential. Persist auth and a seven-day cache; disable public signup and attachments. Caddy supports streaming subscription responses without buffering/timeouts that cut off active streams. [ntfy configuration](https://docs.ntfy.sh/config/).

Default notification mode: one daily digest at 19:00 in a configurable IANA timezone, including all newly shortlisted match and possible_match entries. Setup proposes Europe/London from the current project context and lets the owner change it; never infer timezone from the Ubuntu host. Notification time and collection interval are independent. Daily and twice-daily collection presets are available.

At the scheduled cutoff, snapshot eligible unconsumed events and recheck current availability/assessment/profile versions. Summarize counts by company, up to ten example titles and a link to the full shortlist. Omitted titles are still part of the digest snapshot. Include pending/failed checks separately, so a failure is not reported as zero jobs. Send a concise zero-new-roles summary by default; make empty summaries configurable. Baseline inventories and reassessment results are separately labelled counts/links at this same scheduled time, never immediate floods or misleading new-job alerts.

Events assessed after the cutoff enter the next digest even if the job was discovered earlier. Use durable event membership and a unique owner/local-date digest key, not a sliding last-24-hours query. Once sent, strong-to-possible or possible-to-strong changes do not notify again. If the server is offline at the slot, carry unsummarized events into the next scheduled digest; do not send off-schedule catch-up summaries. Brief transport retries remain attached to the same snapshot, for at most 30 minutes after its slot. Pending, failed or unknown deliveries stay visible; carry definitely unsent events forward, but do not automatically duplicate events in an ambiguous delivery.

Compute each next slot from local calendar date/time using zoneinfo and persist its UTC instant. Keep 19:00 local through daylight-saving changes. For a configurable time that does not exist on a spring-forward day, use the first valid instant after it; for a repeated time, use the first occurrence. Emit at most one scheduled digest per local date, including after schedule edits/restarts. Collectors never publish directly; the ledger separates collection, eligibility, digest membership and delivery.

Guarantee one local event per eligibility key, not exactly-once external push delivery. Retry clearly unsent transient failures. Persist `sending` before the network request. A timeout/crash after a request may have reached ntfy leaves delivery `unknown`; require an explicit resend rather than automatically flooding the topic. The publish-only app credential cannot read the server cache, so v1 does not attempt automatic reconciliation. Recovery converts abandoned `sending` records to `unknown`; the UI explains that a manual resend might duplicate a message. A successful publish records ntfy's returned ID; it proves server acceptance, not that a phone displayed it.

Disable external iOS wake-up forwarding and browser Web Push by default. Foreground browser subscriptions and supported native clients work while connected, but instant iOS background delivery must not be promised. Enabling ntfy's iOS upstream later sends wake-up metadata through an external relay while job contents remain on the local server; this is an explicit owner setting and still requires device access to the private server. [ntfy iOS behaviour](https://docs.ntfy.sh/config/#ios-instant-notifications).

## Resources, backups, and recovery

Initial application sizing estimate: two to four CPU cores, 4–8 GiB RAM and 20 GiB free disk, with extra space for inventory and backups. No model weights or GPU memory are needed. This is an unmeasured starting point; measure browser memory, database growth, concurrent work and API latency. Model choice affects API cost/quality rather than local inference hardware.

Store data in named volumes or an explicitly configured private host data directory. Nightly backups stop mutation-producing services briefly, dump PostgreSQL, and copy documents, ntfy state, and Caddy state as a consistent set; restart services even if backup fails. Keep API keys in separately protected secret backups. Retain seven daily and four weekly encrypted backups on a separate disk/location, with host permissions protecting encryption keys. Test restoration into isolated volumes with scheduling and external notifications disabled before enabling them. Target recovery point 24 hours and recovery time two hours, subject to an actual drill.

Expose DB/migration readiness separately from degraded AI/search/notification status. Log structured operation/source IDs and sanitized errors, never CV text or credentials. Show last successful check, queue age and dependency state in Settings. No monitoring SaaS is required.

## Installation parameters still needed

Actual LAN IP/subnet and local DNS record; tailnet device name/access policy; owner credentials; OpenRouter key and task model IDs (models intentionally chosen later); optional Brave subscription/key; backup destination. Addresses and secrets are deployment values; model choice is the user-requested remaining design selection. No services are installed or running as a result of this document.

## Development-only host-network PostgreSQL override

On the current development machine, the Docker bridge path is unusable. The user approved `compose.test.host.yaml`, applied only with `compose.test.yaml`, to run the disposable PostgreSQL test service on Linux host networking. PostgreSQL itself is explicitly bound to `127.0.0.1:55439`; no port mapping is used. The host backend test URL and PostgreSQL architecture are unchanged. [Docker documents that host networking shares the host namespace and ignores published-port mappings](https://docs.docker.com/engine/network/drivers/host/).

This is an opt-in development exception, not the deployment topology. Do not apply it to production, to fetchers, or to other services without a separate scoped decision. Before deployment on the intended Ubuntu server, validate ordinary Compose service DNS/connectivity, non-published database access, intended LAN/tailnet ingress, and fetcher/private-network isolation. Passing tests with this override does not satisfy those gates.

## Current deployment scaffolding (not release-ready)

`compose.yaml` now declares all ten services, including queue bootstrap, workers, fetcher, proxy, ntfy and edge. `compose.fetch.yaml` is a compatibility no-op. The frontend image and Caddy/ntfy configuration files now exist. Configuration checks pass, but images and the full stack have not been built or runtime-validated. Do not treat these definitions as completed LAN/tailnet deployment. Python, Node, Caddy, PostgreSQL, Squid and ntfy base digests are pinned. ntfy v2.27.0 was pulled successfully and its non-root image was built/checked locally.

The main Compose file pins Squid and configures internal fetch/control networks, no published fetch/proxy ports, a non-root read-only proxy and an independent fetcher credential/state volume. `JOBFINDER_FETCH_ISOLATION_VERIFIED` remains false. `python3 scripts/check-proxy.py` checks literal-address/method/port ACLs using the cached image with `--pull never` and `--network none`, and cleans up its own container. It does not prove DNS rebinding resistance, browser resource isolation or Compose bypass resistance. Those gates must pass before enabling arbitrary fetching; the database host-network exception does not apply to fetching.

Search runtime settings: `JOBFINDER_SEARCH_MODE` defaults to mock; `JOBFINDER_BRAVE_KEY_FILE` names a mounted credential file. Daily/monthly UTC request ceilings default to 300/1000 and can be changed through `JOBFINDER_SEARCH_DAILY_LIMIT`/`JOBFINDER_SEARCH_MONTHLY_LIMIT`. These are application limits, not a claim about the provider account’s billing cycle or allowance. Search reservations/results and cooldown persist in PostgreSQL. Keep current-window ledger records during retention/maintenance; restoring an old database cannot prove unused provider quota. The worker mounts the Brave secret and joins a provider-outbound network. API/AI worker mount the OpenRouter secret; the general worker mounts the ntfy publisher secret. Provider URLs remain fixed in application code; this network is not a domain-allowlisting proxy. Real provider access and credential readability still require deployment validation.


## Implemented notification transport checkpoint

The publisher uses the [documented ntfy POST endpoint](https://docs.ntfy.sh/publish/), a bearer publisher token, a bounded UTF-8 plain-text body and a Click link to the app shortlist. Set `JOBFINDER_NOTIFICATION_MODE=live`, `JOBFINDER_NTFY_URL` (server origin), `JOBFINDER_NTFY_TOPIC`, `JOBFINDER_NOTIFICATION_APP_URL` (app origin) and `JOBFINDER_NTFY_TOKEN_FILE` (default `/run/secrets/ntfy_publisher_token`) when configuring the local service. Default mock mode performs no HTTP and records a definite non-delivery rather than a synthetic server receipt. The app/ntfy origins must be explicit HTTP(S) origins without userinfo, query or fragment; private service HTTP remains permitted inside deployment networks.

Each delivery attempt captures non-secret destination configuration; a changed destination or mode blocks that attempt before credentials are loaded. HTTP environment proxies and redirects are disabled. The body is below ntfy's default 4 KiB limit; all events remain in the digest even when example titles are shortened. A valid matching-topic message receipt records server acceptance, not phone delivery. Missing/invalid receipts, post-connect transport failures and 5xx responses are conservatively unknown. Connection failures and explicit 429 rejections can retry, at most three attempts and no later than 30 minutes after cutoff. Numeric and HTTP-date Retry-After values are preserved; destination cooldowns survive into later digests rather than being shortened to fit the retry window.

The sending state commits before HTTP. Control ticks recover abandoned sending records to unknown, never automatically resend them, and release definitely-unsent terminal events for later scheduled selection. In-flight profile purge erases local summary contents and cancels later work; already-dispatched requests cannot be recalled. Authenticated history exposes the latest attempt and safe receipt/error fields. Dedicated manual resend/test-message endpoints and notification Settings controls are implemented. Real local ntfy acceptance and deployment wiring remain pending.

Explicit owner resends retain the original dated summary and start a fresh three-attempt window ending 30 minutes after the request. An unknown original outcome requires duplicate acknowledgement; if that resend fails definitely, the original uncertainty and event reservations remain. Standalone test messages use the same transport, destination cooldown and recovery rules without changing daily digest membership. Scheduled delivery can be disabled while the owner explicitly tests or resends. Mock mode never publishes or records a synthetic successful receipt.

## Preparing the Ubuntu deployment (configuration implemented; runtime gates pending)

Run these preparation steps on the intended host after its dependency access is established. They are not evidence that deployment has run here:

```bash
python3 scripts/init-deployment.py
# Edit deploy/.env: actual LAN_IP, LAN_HOST and TAILNET_HOST; review the pinned ntfy release.
python3 scripts/check-deployment.py --env-file deploy/.env
```

Initialization preserves existing files and permissions. It creates random DB/fetcher credentials only when missing, empty provider/publisher files, and a non-secret deployment parameter file. It does not read or import the development root .env. Keep `.secrets` owner-only (0700). File-backed Compose secrets preserve host permissions: their files must be readable by the mounted container users, including UID 10001 and PostgreSQL. New files use 0644 **inside that private directory**; existing mode-0600 files need explicit adjustment before deployment. Do not make the directory public or move readable secret files outside it. Each service receives only its declared secrets. Preflight verifies host directory/file permissions and requires nonempty credentials when the corresponding live mode is selected; it cannot prove successful provider authentication.

With no arguments, `scripts/check-deployment.py` checks the template using synthetic host values and the pinned ntfy base. It neither pulls nor starts anything. With `--env-file`, it also checks actual secret files. Image builds, credentials and service connectivity remain separate gates.

After preflight, successful image builds and resolution of the runtime blockers:

```bash
docker compose --env-file deploy/.env build
docker compose --env-file deploy/.env up -d
docker compose --env-file deploy/.env exec api python -m app.cli create-owner
```

Dependency failures remain stop-and-report events. Current npm and uv lockfiles contain private package-registry URLs; an off-network host needs portable lockfiles prepared and verified there before building. No registry rewrite or certificate workaround was performed in this development environment. The backend image still provides HTTP-only fetching; a browser-enabled image remains pending the Python Playwright dependency gate.

Create two regular ntfy accounts through its local CLI: `publisher` and `reader`. Grant only `publisher <topic> write-only` and `reader <topic> read-only` using `ntfy access`; issue a publisher token and store it privately in `.secrets/ntfy_publisher_token`. Use the reader account in the ntfy client. Account creation, token storage and actual denied/allowed access checks remain installation steps; no credentials are embedded in the YAML. The shipped config denies anonymous access, retains a seven-day cache and leaves attachments, external wake-up and Web Push disabled. Refer to the [ntfy authentication configuration](https://docs.ntfy.sh/config/#access-control).

The edge maps only the configured RFC1918 LAN address (443/8443) and loopback (8080/8081). The internal container TLS listener ports are 8443/9443, allowing non-root Caddy with all capabilities dropped. Follow the earlier host Tailscale Serve and Docker-aware firewall steps; they are not installed automatically. API cookies stay Secure while Caddy/Tailscale terminate TLS. The API ignores forwarded headers and accepts only explicit configured hosts/origins. Caddy streams ntfy responses with [flush_interval](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming) configured for immediate flushing.

Fetcher's `JOBFINDER_FETCH_ISOLATION_VERIFIED` remains hard-coded false. Internal networks and Squid are configured, but the required worker-to-fetcher-only stateful firewall boundary is not installed or verified. Do not enable fetching until same-bridge bypass/private-range/DNS/browser checks pass on the intended host. Do not extend the development database host-network exception.

The initial non-root Caddy check failed with `exec /usr/bin/caddy: operation not permitted` (exit 255). Inspection identified the inherited `cap_net_bind_service=ep` file capability. The runtime-base image removes it because all container listener ports are above 1024. That stage builds from the cached base, and Caddy adapt/validation now passes under the same non-root, read-only, cap-drop-ALL, network-none restrictions. This is resolved image configuration, not a host-security/network workaround. Full static serving, API routing, TLS client trust and host ingress remain unverified.

The non-root ntfy image builds offline from the pinned cached base, owns its state directory, and has a health check. `python3 scripts/check-ntfy.py` validates a disposable network-none server with synthetic credentials: anonymous denial, publish-only bearer-token access, rejection of publisher reads/unrelated topics, reader-only cached-message access and a matching receipt. It removes its own temporary container and never publishes ports or contacts real devices. These checks do not prove app-worker-to-ntfy Compose delivery or phone notification delivery. Normal Compose connectivity, backup/restore and full application image builds remain open.

## Basic encrypted backup and isolated restore

Use an existing owner-only directory (mode 0700) on the backup disk and a dedicated GPG home (also 0700). Import the selected recipient's public key there; use its full fingerprint. Keep its private decryption key and a separately protected copy of deployment secrets off the application host. These scripts require installed GPG, Docker/Compose and the pinned cached Python/PostgreSQL images; they never fetch images. An unattended backup needs only the public key. Restore requires an available private key and, for a protected key, an unlocked GPG agent.

```sh
python3 scripts/backup.py --env-file deploy.env \
  --destination /private/backup-directory --gpg-home /private/backup-public-keyring \
  --recipient FULL_RECIPIENT_FINGERPRINT
python3 scripts/backup.py --verify /private/backup-directory/jobfinder-SNAPSHOT \
  --gpg-home /private/restore-keyring
python3 scripts/restore.py --backup /private/backup-directory/jobfinder-SNAPSHOT \
  --gpg-home /private/restore-keyring --record-directory /private/empty-restore-record
```

Backup pauses mutation-producing services, streams the database dump and five state volumes directly through encryption, and attempts to restart only previously active services. Run it during a quiet period without concurrent deployment/container changes. A successful directory is named `jobfinder-*`; `.incomplete-*` indicates failure and must not be treated as a completed backup. The private `operation.json` records restart failures and container identities. Following power loss or a forced kill, inspect this journal and actual container state and resume the listed services using the original deployment configuration; process cleanup cannot recover from SIGKILL or host failure automatically. A destination-local lock prevents overlapping backups to the same directory, including from different checkouts. Do not run concurrent backups of one deployment to different destinations.

Verification checks encrypted payload integrity, not backup provenance or application correctness. Restore only backups from a trusted location: possession of the public encryption key alone can produce a new encrypted archive. No plaintext staging files are created, but restored volumes necessarily contain private plaintext data and must remain protected.

Restore refuses a nonempty record directory, creates fresh UUID-named volumes, and never overwrites deployment volumes. Extraction rejects links/special files and path escapes, with private permissions and application ownership. PostgreSQL uses a network-none container with TCP listening disabled. Application services, schedules and notifications are not started. Temporary containers are removed; restored volumes remain listed in the private journal, including partial volumes if restoration fails. Preserve those names for deliberate cleanup or recovery; never use a broad volume-prune command.

The synthetic drill checks files from every state archive and a restored database row. This does not prove an operational application restore. Before cutover on the intended server, verify schema/application compatibility, document availability and owner login in an isolated deployment, reestablish the database password from separately protected secrets, and account for external provider usage and potentially already-delivered notifications since the snapshot. Keep workers and outbound delivery disabled until that reconciliation is complete. Deliberately attach the validated restored volumes only during the recovery maintenance window. Automated cutover and a full deployed-application restore drill remain pending; the 24-hour recovery-point/two-hour recovery-time targets are unmeasured.


## Nightly scheduling and retention

The supplied `deploy/systemd/jobfinder-backup.service` and `.timer` are installation templates, not enabled services. Defaults assume the checkout is `/opt/find-job`, the deployment account/group is `jobfinder`, and `/etc/jobfinder/backup.env` contains the three values from `deploy/systemd/backup.env.example`. Adapt those paths and account names to the intended host. The account must own the private backup/keyring directories, read the deployment configuration/secrets, and already have Docker access. Use the same deployment account for manual and scheduled backups.

The timer runs at 02:00 in the host timezone, with up to ten minutes of jitter. `Persistent=true` schedules one catch-up after missed downtime. This host-maintenance schedule is independent of the app's configurable 19:00 notification timezone. Change `OnCalendar` if desired. The service has a three-hour maximum runtime and allows fifteen minutes for termination cleanup; `KillMode=mixed` initially signals the Python parent so it can attempt to resume writers. A forced kill/power loss still requires journal-based recovery.

After a manual backup and isolated restore have succeeded on the intended host, install the adapted service/timer in `/etc/systemd/system/` and the configuration in `/etc/jobfinder/backup.env`. Then run:

```sh
sudo systemd-analyze verify /etc/systemd/system/jobfinder-backup.service /etc/systemd/system/jobfinder-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now jobfinder-backup.timer
systemctl list-timers jobfinder-backup.timer
journalctl -u jobfinder-backup.service
```

Installation and an actual scheduled run remain host acceptance tasks. This development session only checked unit syntax/calendar parsing; it did not install accounts, units or host configuration. Check service failures and available backup space rather than assuming an enabled timer proves a valid snapshot.

`--retain`, included in the service template, prunes only after the current backup succeeds. It retains the newest available snapshot for each of seven UTC dates and four ISO weeks; daily/weekly selections may overlap. It does not make duplicate weekly copies. A public-key-only host checks expected private file layout and completion journal, not decryption integrity; keep performing private-key verification/restore drills. Unexpected directories, incomplete snapshots, other projects, future dates, symlinks/hardlinks and non-private files are untouched and require manual review. They can consume disk space indefinitely. Backups and decryption keys still need a separately protected/off-host copy.

Preview the current deletion candidates without changing anything:

```sh
python3 scripts/retention.py --destination /private/backup-directory --project jobfinder
```

Use the actual Compose project name if changed. The preview is a point-in-time selection, not authorization to delete arbitrary paths. Without `--retain`, the backup command never prunes. Keep the backup destination owner-only and do not modify its contents during a backup/retention run.
