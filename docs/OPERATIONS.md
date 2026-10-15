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

## Logs and retention

SQLite stores up to 2,000 log entries per job. The Swift agent buffers at most 500 pending lines and sends bounded batches; high-volume output is bounded with an explicit overflow marker. Unsent batch tails are retained; individual lines are limited to 2,000 Unicode scalars. Do not put secrets in prompts or runtime output. Events, jobs and metering history are not automatically pruned in this release. Plan retention and backup policy before long-lived deployment.

Stop the server before copying its database, or use SQLite's backup API. Preserve the database and its permissions on restart. Do not remove a live WAL file. Restored reservations expire through the normal lease logic.

## Inference replicas

Allowlist origins in the control-plane configuration. Only administrators may register endpoints. The gateway performs least-in-flight selection, not performance prediction, automatic failover or health-based removal. It never forwards platform bearer tokens. Connect remote workers through a secured private network or tunnel. Avoid publicly exposing unauthenticated model servers.

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
- **No automatic schedule:** nothing evicts by itself. To sweep on a schedule, run the POST from cron or launchd.
- **Capacity numbers:** `/api/capacity` reports online nodes, budget/reserved/free GiB and queued/running counts. `reservedPct` is reservations divided by budget, not measured GPU utilisation.

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
