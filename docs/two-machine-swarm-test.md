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

## test steps (turnkey — web ui, no terminal required)

run the web app on BOTH machines. the swarm is formed from the
coordinator's UI: every machine broadcasts itself over udp, and the
coordinator discovers peers, handshakes, and plans the layer split — all
from buttons. the live node inventory in the swarm tab is real: it shows
this device plus every node broadcasting on the LAN (no demo devices).

### step 1 — windows machine (peer, stick in D:\)
1. double-click `START_OFFGRIDUSB_WINDOWS.bat` and open the web app (the
   console window prints the local url).
2. go to the **Swarm tab** and click **Start Node** under "Live Swarm Node
   Control". leave RAM/VRAM/Arch blank — the app auto-detects this
   machine's real hardware (no fake 4096 MB default).
3. leave the app running. this machine is now broadcasting on the LAN.

### step 2 — nixos/linux machine (coordinator)
1. run `./run_linux.sh` (or `START_OFFGRIDUSB_LINUX.sh` on a stick) and
   open the web app.
2. go to the **Swarm tab** and click **Start Node** here as well (both
   machines broadcast; the watchdog tracks peer health on both sides).
3. the **live node inventory** at the top now lists both devices (this
   device + discovered peers) with ONLINE badges. verify both appear.
4. click **Form Swarm Cluster**. discovery → TCP handshake → layer-split
   planning run automatically; the plan card shows pooled RAM/VRAM and
   the unlocked tier.

### step 3 — launch distributed inference (optional, coordinator side)
1. on the same swarm tab, use the "Launch Distributed Inference" card:
   pick a model from the dropdown, click **Launch Cluster Inference**,
   then type a prompt and click **Run Completion**. the UI starts
   `ggml-rpc-server` on every peer's web app (port 50055) and runs
   `llama-server` locally with a proportional `--tensor-split`. zero
   terminal commands.

### legacy cli fallback (debug / headless)
for headless machines (e.g. a vps) or isolating transport problems, the
manual flow still works:
```bash
# node side (either machine)
PYTHONPATH=src python3 -m emyrge.swarm node --id <name> --port 50052 \
    --rpc-port 50053 --ram-mb <ram> --vram-mb <vram> --arch x86_64 &

# coordinator side (explicit seeds skip udp discovery)
PYTHONPATH=src python3 -m emyrge.swarm coordinate --json \
    --seed <peer-lan-ip>:50052 --seed 127.0.0.1:50052
```
the `--seed` path bypasses broadcast discovery (the most likely failure
point) — use it to separate transport problems from clustering problems.

## pass criteria
- 2/2 handshakes OK
- `cluster_formed: true`
- `pooled_ram_mb` equals the SUM of both machines' declared ram
- `unlocked_tier` is higher than either machine reaches alone (run each
  machine solo once first to capture the baseline)
- `layer_split` assigns layers to BOTH nodes (proportional to memory)
- `rpc_command` references both node ips
- optional: `--simulate-drop` from the coordinator kills one node from the
  plan and re-unlocks a lower tier — validates the node-drop fallback live.

## honest limits (not yet tested)
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

## live run results (2026-11-02)

**vps ↔ nixos (tailscale, seed mode):** 2/2 handshakes OK, cluster formed. pooled_ram_mb 39468 = 31832 (nixos) + 7636 (vps) ✓
effective_pool_mb 51756 → tier 4 unlocked, ring topology spans both nodes, layer_split 68/12 proportional to memory, rpc_command references both ips ✓
`--simulate-drop`: vps-node dropped from plan, rebalanced to 1 node (DEGRADED_AUTO_RECOVERED), no crash ✓
tier-difference demo with constrained profiles (8000 MB declared each): solo = tier 2, pooled = tier 3 with a 32/32 layer split ✓

**3-machine run (windows + nixos + vps, seed mode):** 3/3 handshakes OK. pooled_ram_mb 55692 = 16224 (windows) + 31832 (nixos) + 7636 (vps), pooled_vram 16384 (12288 RTX3060 + 4096 GTX1660S), effective_pool_mb 72076 → tier 4. ring: windows L0-22, nixos L23-71, vps L72-79; split 28.2/61.2/10.6% proportional. windows SOLO baseline = tier 3 (eff 20320) → pooling across machines unlocked tier 4 ✓. simulate-drop of vps-node rebalanced the remaining 2 nodes cleanly ✓.

windows leg notes:
- ssh access: user `19032`, auth is the **ovhcloudvps key** (`~/.ssh/ovhcloud1p` on the vps) — passwords don't work.
- stick is at `D:\` with portable python at `D:\bin\windows_x86_64\python\python.exe`; stick layout has src/ at root so PYTHONPATH=D:\src is needed.
- firewall rules (udp/50051 + tcp/50052-50053 in) added via netsh and they persist across reboots.
- detach gotcha: Start-Process/bat-file routes exit instantly with no error; run the node in the foreground of a backgrounded ssh session instead (`ssh -f winbox "cmd /c ..."`).
- stick runtime.py was stale (pre announce-interval fix); synced from repo main.

remaining untested limit (unchanged): actual llama.cpp rpc completion across nodes.

## windows stick sync (2026-11-02 16:05)
stick re-synced from repo main (d851542): scp'd src/emyrge + web/static.
verified on stick: src/emyrge/swarm/inference.py (SwarmInference class present),
web/static/app.js (swarmInfLaunch handlers present), watchdog.py, runtime.py.
stick and repo are now byte-identical for the swarm code paths.
