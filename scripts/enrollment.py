# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""Redeem a single-use join code for a per-node agent token (standard library only)."""
import json, re, socket, urllib.error, urllib.parse, urllib.request

NODE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

def default_node() -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", socket.gethostname().split(".")[0]).strip("-._")
    return name[:63] or "mac"

def redeem(server: str, code: str, node: str, timeout: float = 10.0) -> str:
    u = urllib.parse.urlsplit(server)
    if u.scheme not in ("http", "https") or not u.hostname or (u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1")):
        raise SystemExit("remote server requires HTTPS (or use http://127.0.0.1 with an ssh tunnel)")
    if not NODE_ID.match(node): raise SystemExit("invalid node id: use letters, digits, '.', '_' or '-'")
    req = urllib.request.Request(server.rstrip("/") + "/api/enroll", data=json.dumps({"code": code, "node": node}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)["token"]
    except urllib.error.HTTPError as e:
        try: why = json.load(e).get("error", "")
        except ValueError: why = ""
        raise SystemExit(f"enrolment refused (HTTP {e.code}): {why}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise SystemExit(f"cannot reach {server}: {getattr(e, 'reason', e)}") from None
