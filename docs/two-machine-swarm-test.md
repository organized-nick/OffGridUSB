# two-machine swarm test runbook (linux + windows)

goal: run the emyrge swarm on two real machines at once and confirm the
cluster pools both machines' RAM/VRAM and unlocks a higher model tier.

current swarm plumbing (all in `src/emyrge/swarm/`, verified green on loopback):
- `SwarmNode` — UDP announcer (broadcast + loopback) + TCP handshake responder
- `CoordinatorDiscovery` — listens for announces on udp/50051
- `CoordinatorRuntime` — handshake each peer, `ClusterCoordinator.plan_cluster()`
- web app (`src/emyrge/web/app.py`) exposes it in the UI:
  - `GET /api/swarm/status`
  - `POST /api/swarm/node/start` / `node/stop`
  - `POST /api/swarm/scan` (discover -> handshake -> plan)

tier unlock thresholds (pooled effective MB = ram + vram, non-metal only):
- < 3,000:   tier 0 — qwen2.5-0.5b (emergency fallback)
- < 10,000:  tier 2 — qwen2.5-7b
- < 42,000:  tier 3 — qwen2.5-32b (swarm frontier)
- >= 42,000: tier 4 — llama-3.3-70b (settlement supercluster)

so: linux box with 32gb ram + windows box with 32gb ram alone = tier 3.
to see a *difference from single-machine*, at least one machine should
contribute enough pooled memory to cross a threshold the other doesn't
reach alone (e.g. 16gb + 16gb -> tier 3 pooled, tier 2 alone).

## prerequisites

1. both machines on the same LAN (UDP broadcast must reach both — same
   wifi/ethernet subnet, no AP isolation). tailscale is NOT enough for
   discovery (it's L3), but works as our ssh access path.
2. the offgridusb package (repo or provisioned stick) present on both.
3. python 3.10+ on both (stdlib only, no pip deps needed for swarm).
4. windows firewall must allow udp/50051 in + tcp/50052,50053 in for the
   swarm node. easiest:
   ```bat
   netsh advfirewall firewall add rule name="offgrid-swarm" dir=in action=allow protocol=UDP localport=50051
   netsh advfirewall firewall add rule name="offgrid-swarm-rpc" dir=in action=allow protocol=TCP localport=50052-50053
   ```
   (run powershell as admin). check linux side too: `sudo ufw allow 50051:50053/udp` + tcp if ufw is enabled.

## test steps

### 1. linux machine
```bash
cd <stick-or-repo-root>
# start the web app (has the swarm control card) — or headless CLI:
# note: repo checkout uses a src/ layout — PYTHONPATH=src is required there.
# on a provisioned stick where emyrge/ sits at the root, drop the env var.
PYTHONPATH=src python3 -m emyrge.swarm node --id linux-node --port 50052 --rpc-port 50053 \
    --ram-mb <actual-ram-mb> --vram-mb <actual-vram-mb> --arch x86_64 &
# get real numbers: free -m | awk 'NR==2{print $2}'
```
or start the web app (`./run_linux.sh`) and click "start node" on the Live
Swarm Node Control card, filling ram/vram (the API takes ram_mb/vram_mb;
default 4096/0 is a lie for real hardware — pass real values).

### 2. windows machine (stick in D:)
```bat
cd /d D:\
python -m emyrge.swarm node --id windows-node --port 50052 --rpc-port 50053 ^
    --ram-mb <actual-ram-mb> --vram-mb <actual-vram-mb> --arch x86_64
```
get real numbers with `wmic ComputerSystem get TotalPhysicalMemory` or
systeminfo. for a discrete GPU add its vram in mb (nvidia-smi).

### 3. form the cluster (from the linux machine)
```bash
PYTHONPATH=src python3 -m emyrge.swarm coordinate --json \
    --seed <windows-lan-ip>:50052 --seed 127.0.0.1:50052
```
(the --seed path skips broadcast discovery, which is the most likely
failure point; use it to isolate transport from clustering).
or hit `POST /api/swarm/scan {"window":3}` on the web UI.

### 4. pass criteria
- 2/2 handshakes OK
- `cluster_formed: true`
- `pooled_ram_mb` equals the SUM of both machines' declared ram
- `unlocked_tier` is higher than either machine reaches alone (run each
  machine solo once first to capture the baseline)
- `layer_split` assigns layers to BOTH nodes (proportional to memory)
- `rpc_command` references both node ips
- optional: `--simulate-drop` from the coordinator kills one node from the
  plan and re-unlocks a lower tier — validates the node-drop fallback live.

### 5. what is NOT tested yet (honest limits)
- an actual llama.cpp rpc completion routed across both machines — the
  runtime plans and launches workers (`RpcWorkerLauncher`) but no end-to-end
  model inference across the 2 nodes has been executed. for that we need
  llama-rpc-server binaries bundled on both machines + a small gguf.
- udp broadcast across the LAN (worst case: apartment router blocks
  broadcasts — then use `--seed` mode only; it's functionally equivalent
  minus zero-config discovery).

## troubleshooting
- "connect failed: refused" on windows handshake → firewall rule missing or node not started (check `GET /api/swarm/status`).
- discovery finds 0 nodes but seed handshake works → broadcast blocked (router/windows firewall) — fine, use seeds.
- node announces but handshake replies with loopback ip 127.0.0.1 in rpc_command → coordinator uses the ip you handshook with, so always seed real LAN ips for cross-machine runs.
- broadcast discovery blocked (router/AP isolation) → use `--seed` mode; it's functionally equivalent minus zero-config discovery. seeds also work over tailscale (L3), as verified in the live run below.

## live run results (2026-11-02, vps ↔ nixos over tailscale, seed mode)
- 2/2 handshakes OK, cluster formed. pooled_ram_mb 39468 = 31832 (nixos) + 7636 (vps) ✓
- effective_pool_mb 51756 → tier 4 unlocked, ring topology spans both nodes, layer_split 68/12 proportional to memory, rpc_command references both ips ✓
- `--simulate-drop`: vps-node dropped from plan, rebalanced to 1 node (DEGRADED_AUTO_RECOVERED), no crash ✓
- tier-difference demo with constrained profiles (8000 MB declared each): solo = tier 2, pooled = tier 3 with a 32/32 layer split ✓
- windows machine NOT covered: tailscale ping ok, tcp/22 open, but password auth rejected for the documented user — credentials need refreshing before the windows leg runs.
- remaining untested limit (unchanged): actual llama.cpp rpc completion across nodes.
