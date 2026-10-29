# Operating a trusted Mac fleet

## Identity and deployment

Use separate random agent tokens for each node. Keep the server configuration, credential environment file and generated launchd plist private (0600). The plist stores the agent credential for launchd; anyone who can read it can impersonate that node. Rotate credentials by changing the server configuration and restarting both the server and affected worker. This version does not offer online token rotation or OIDC.

The server binds to loopback by default. Use the built-in TLS listener with trusted certificates for remote access. The Docker image requires mounted certificates, configuration and a writable volume for UID 10001. The development HTTP server is suitable for evaluation; put appropriate request-rate, connection and body-timeout protections at your HTTPS ingress before exposing it to a large network.

## Runtime trust

Job submitters can choose the allowed runtime's arguments and model paths. Enable this only for trusted teams. A runtime can read/write files as its agent user. There are no per-job OS user accounts, sandbox entitlements or network isolation. Use a dedicated non-admin macOS user and local directories with correct ownership. Do not enable model custom-code loading or backgrounding launchers.

The model registry documents models and inference replicas; it does not automatically download or cryptographically verify model artifacts. Pin/checksum models yourself. Runtime installations and model licenses are your responsibility. The examples intentionally contain editable absolute paths.

## Admission and cancellation

Drain stops new claims and preserves active jobs. Cancel sends a request acknowledged during worker renewal. Both server and agent enforce the per-attempt timeout. The server signals cancellation at the deadline and refuses renewal beyond a 20-second grace. Capacity stays reserved until completion or lease expiry; timeout failures follow the configured retry limit. Default retries are zero; enable only when the workload is safe to repeat. GPU kernel cancellation latency is controlled by the framework/driver, so there is no guaranteed hardware preemption SLA.

Do not sleep your Mac workers during active jobs. Before restarting a worker, drain and cancel its active workload, then confirm the child has exited. If the worker disappeared unexpectedly, inspect its direct process and kill any survivor before reopening admission. Database fencing cannot prove that a surviving process has stopped using Metal.

## Using TLS on a home or office network

A control plane that other Macs reach must serve HTTPS (the Swift agent and desktop app refuse plain HTTP to anything but loopback). Without a public domain, a small private CA works:

```sh
# once, on any Mac: a CA and a server certificate whose names match how agents reach the server
openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 365 -subj "/CN=Gryvia LAN CA"
openssl req -newkey rsa:2048 -nodes -keyout srv.key -out srv.csr -subj "/CN=studio.local"
printf "subjectAltName=DNS:studio.local,IP:192.168.1.20\nextendedKeyUsage=serverAuth\n" > ext.cnf
openssl x509 -req -in srv.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out srv.crt -days 365 -extfile ext.cnf
chmod 600 ca.key srv.key
python3 -m server.app --config config.json --host 0.0.0.0 --port 8443 --cert srv.crt --key srv.key
```

Then trust `ca.crt` on every Mac that talks to the server (agents, the desktop app, the CLI): `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ca.crt`. Keep `ca.key` offline once the certificates are issued, and renew before `-days` runs out (an expired certificate stops every agent). Use the name or address in the certificate's `subjectAltName` in `--server` and in the join command.

The server accepts TLS 1.2 or newer. Mutual TLS (client certificates for agents) is not implemented; agents authenticate with their bearer token, so keep the network trusted and revoke a lost Mac with `gryvia revoke-node`.

**Verified (dev Mac, loopback):** with a certificate made by the recipe above, the server answered `/healthz` to a client that trusted the CA, a client without the CA got `CERTIFICATE_VERIFY_FAILED`, and a TLS 1.1-only client could not connect. **Not verified:** the `security add-trusted-cert` step, the Swift agent or desktop app against a private-CA server, certificate renewal, and any non-loopback address.

## Logs and retention

SQLite stores up to 2,000 log entries per job. The Swift agent buffers at most 500 pending lines and sends bounded batches; high-volume output is bounded with an explicit overflow marker. Unsent batch tails are retained; individual lines are limited to 2,000 Unicode scalars. Do not put secrets in prompts or runtime output. Events, jobs and metering history are not automatically pruned in this release. Plan retention and backup policy before long-lived deployment.

### Backup and restore

`gryvia backup [--keep N]` (admin) asks the server to write a consistent snapshot of the whole database (`VACUUM INTO`, so one self-contained file) into `backupDir` from `config.json`, default `backups/` next to the database. Files are `gryvia-YYYYmmdd-HHMMSS[-N].db`, mode 0600 in a 0700 folder, integrity-checked when written, newest N kept (default 7, at most 100). The client cannot choose a path. Only files matching that name pattern are ever pruned.

The snapshot holds job specs and logs, hashed enrolment and agent tokens, and pinned node keys, but not `config.json` tokens. It lives on the control-plane Mac, so it does not protect against losing that Mac: copy it elsewhere on a schedule, for example a launchd job running `gryvia backup` then `rsync`.

To restore: stop the server, delete the live `gryvia.db`, `gryvia.db-wal` and `gryvia.db-shm`, copy the chosen snapshot to `gryvia.db`, start the server. Reservations from before the snapshot expire through the normal lease logic; agents re-register on their next heartbeat. Restoring has been tried only by opening a snapshot as a store in the tests, not on a full running fleet. Otherwise: stop the server before copying its database, preserve its permissions, and never remove a live WAL file.

### Lost jobs after an agent restart

Agents report the job ids they are executing in each heartbeat. If the server believes a Mac is running a job that the Mac no longer reports (and the claim is more than 10 seconds old), it releases the job through the normal lease-expiry path at once instead of after the lease runs out: retried if retries remain, otherwise failed. This frees bookkeeping only. It does not prove the old process has stopped; check the Mac before assuming the GPU is free. Agents older than this change send no list and are not reconciled.

## Inference replicas

Allowlist origins in the control-plane configuration. Only administrators may register endpoints. The gateway performs least-in-flight selection, not performance prediction or health-based removal. It tries one other replica before the first byte; there is no mid-stream failover. It never forwards platform bearer tokens. Connect remote workers through a secured private network or tunnel. Avoid publicly exposing unauthenticated model servers.

The concurrency cap is per authenticated tenant. Administrator requests use the default tenant. Model markings apply to both tenant and administrator inference calls. Text requests have bounded message count, character count and max output tokens. Streaming (`"stream": true`, SSE) is forwarded. Tools/function calls are not: the gateway forwards only `model`, `messages`, `max_tokens` and `stream`.

Managed deployments from a current agent use the outbound relay. The model server stays on the worker's loopback, and the agent carries requests and responses over its own authenticated polling connection, so no worker port or origin allowlist entry is needed. Older agents keep the allowlisted direct-HTTP path. Upgrade the controller and agents together.

## Idle eviction and capacity

Deployed models keep their reservation until their serve job ends. To free memory held by replicas nobody is using, list and evict them. Both calls are administrator-only:

```bash
curl -fsS -H "Authorization: Bearer $GRYVIA_ADMIN_TOKEN" 'http://127.0.0.1:8443/api/models/idle?seconds=3600'
curl -fsS -H "Authorization: Bearer $GRYVIA_ADMIN_TOKEN" -H 'Content-Type: application/json' \
     -d '{"seconds": 3600, "reason": "nightly idle sweep"}' http://127.0.0.1:8443/api/models/evict-idle
curl -fsS -H "Authorization: Bearer $GRYVIA_ADMIN_TOKEN" http://127.0.0.1:8443/api/capacity
```

- **What counts as idle:** a model is idle when no gateway request (completed or streamed) and no deployment for it has been recorded within `seconds` (0 to 30 days). Traffic that bypasses the gateway, such as direct calls to a worker's loopback port, is not seen.
- **What eviction does:** it cancels the model's serve jobs, the same as `undeploy`. The reservation is released when the agent acknowledges. The model returns to `ready`, and later requests get 503 until it is deployed again. The next request does not redeploy it automatically.
- **Automatic eviction (opt-in, off by default):** set `autoEvictIdleSeconds` in `config.json` (or start the server with `--auto-evict-idle SECONDS`) to 0 for off, or 60 seconds to 30 days. A daemon thread in the control plane then runs the same transactional eviction every `autoEvictIntervalSeconds` (default 60), logs only a count, and records `model.evict_idle` events with the reason `auto idle eviction`. Without the setting nothing evicts by itself. The window is measured from gateway requests only, so choose it well above your longest quiet period.
- **Dashboard:** Overview → Idle deployments lists what a chosen window would evict and has a two-click Evict button (admin token).
- **Capacity numbers:** `/api/capacity` reports online nodes, budget/reserved/free GiB and queued/running counts. `reservedPct` is reservations divided by budget, not measured GPU utilisation.

## Replicas

`gryvia.py deploy MODEL --node A --node B` submits one serve job per Mac (up to 8; each Mac needs the artifact, see `stage`). Each job that reports an endpoint becomes a replica on the model record, and the gateway sends each request to the replica with the fewest requests in flight. If a replica is unreachable or answers badly, the gateway tries one other replica before returning 502; streams fail over only before the first byte, never mid-stream. When one replica's job ends the others keep serving. `undeploy` and idle eviction stop every replica. There is no autoscaler and no reconciliation that replaces a lost replica.

## Hardware acceptance checklist

1. Run `scripts/mac-smoke.sh`, confirming the actual Swift subprocess lifecycle.
2. Run a small pinned MLX model and verify logs, output and allocator metrics.
3. Cancel a deliberately long job; verify the direct child exits and capacity is released.
4. Disconnect the server and verify the agent stops on renewal failure.
5. Confirm configured budgets leave headroom for macOS and expected model/KV-cache peaks.
6. Test two real Macs, TLS identities, drain and independent-job dispatch.
7. Benchmark native MPS/MLX performance; do not publish fixture or CPU-demo figures as GPU results.


## Owner policy, energy and provenance

```bash
python3 scripts/gryvia.py policy my-mac --mode idle --idle-minutes 10 --allow-battery no   # run only when I am away
python3 scripts/gryvia.py nodes                                                            # shows POLICY and WORK ALLOWED
python3 scripts/gryvia.py provenance my-model                                              # signed chain
python3 scripts/gryvia.py rekey my-mac                                                     # after reinstalling an agent
make power-helper                                                                          # optional, asks for sudo: energy estimates
python3 -m server.app --config local/config.json --db local/gryvia.db --require-verified   # deploy gate
```
