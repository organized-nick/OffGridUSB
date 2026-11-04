# live rpc pooled-inference run (2026-11-02)

## tier-3 update (2026-11-03) — Qwen2.5-32B pooled run: SUCCESS

windows host + nixos rpc node, split 6656/44120 (host/nixos), b11913 everywhere:

```
host:   windows  llama-server :8083 -m C:\Users\19032\Downloads\Qwen2.5-32B-Instruct-Q4_K_M.gguf --rpc 192.168.8.157:50055 --tensor-split 6656,44120 -ngl 99 -c 8192
rpc:    nixos    ggml-rpc-server :50055 (binary auto-extracted from bin/linux_x86_64/llama-ubuntu-x64.tar.gz)
```

- completion verified, multi-turn stable. nixos rpc-server RSS climbed to 17.2GB = its 44120/50776 share — remote compute genuinely load-bearing.
- **model source matters: the USB/exFAT stick is unusable as a live model source for tier-3.** llama-server launched against D:\data\models\Qwen2.5-32B spun one core for 9+ min without opening a single rpc connection (metadata scan over slow USB); the identical file from the local SSD (C:\Users\19032\Downloads) connected rpc immediately and finished load in ~7 min. run tier-3 from a local-disk copy of the gguf.
- load takes ~7-8 min (nixos fetches its 17GB share over the usb-eth LAN link during load). /health returns 503 "Loading model" until ready — poll, don't restart.
- port 8081 is kiwix on the windows stick — use 8083 for manual hosts.
- app-spawned (UI /api/swarm/inference/start) tier-3 still has a gap: the UI-launched host hung the same way the stick-source launch did, and the single-threaded HTTP handler blocks the whole web app while start waits. binary-discovery bugs on that path are fixed in OffGridUSB PR #14 (exe-vs-impl.dll preference, rpc-server tar fallback trying all archives, stable /tmp extraction slots) — next step: point the UI at local-disk model copies and/or background the start handler.
- FIXED (swarm-ui-tier3-local branch): the model picker + default pick now scan well-known local-disk model dirs too (windows: %USERPROFILE%\Downloads and %USERPROFILE%\swarm-tools\models; linux: ~/models and ~/.local/share/emyrge/models) and prefer them over data/models (the stick) — a UI-launched tier-3 run loads from the SSD with zero terminal commands. The start handler is backgrounded (start_async): the HTTP response returns instantly with {"ok":true,"starting":true} and the UI shows STARTING while the launch runs; outcome surfaces via status().inference.starting/last_error. Bonus fix: windows RAM autodetect switched from a flaky PowerShell spawn to ctypes GlobalMemoryStatusEx (instant, cached) — no more ram_mb 0 → 4096 advertised.
- windows RAM autodetect is flaky (returned 0 → node advertised the 4096 default); stop/start the node with explicit ram_mb/vram_mb if the plan looks wrong (16224/6144 on this box).
- boot wedge root cause (2026-11-03 evening, john reported "launch hanging, might be loading the 32B and failing"): app boot auto-selects the highest-tier staged model for the LOCAL 8082 llama-server — with the 32B on the stick that's a guaranteed wedge. Fixed in OffGridUSB PR #16 (merged): discover_model skips ggufs larger than available physical RAM (tier walk + size fallback); explicit env overrides unaffected. 5 tests (tests/test_model_boot_guard.py). Windows box now boots picking qwen2.5-1.5b.
- ALSO: the fragile launch route was killing the app silently — Start-Process with -RedirectStandardOutput dies within ~2min when the spawning ssh/powershell exits (broken stdout handle on the HTTP log lines). Use the CIM Win32_Process.Create route (detached, cmd >> redirection) like the previous sessions did. Verified: app survived 2.5min+ with announces flowing via CIM spawn.
- windows box current state after fix: app :8000 up (PID via CIM, cmd >> log redirect), local LLM = qwen2.5-1.5b on 8082, swarm node started with explicit 16224/6144, nixos discovers offgrid-12644.
- teardown: taskkill /F /IM llama-server.exe on windows + pkill -f ggml-rpc-server on nixos; frees ~19GB on the windows box (it was down to 487MB free during the run).

victory condition from john: first actually-run pooled inference on the swarm.

## result — SUCCESS

three-machine pooled inference across the tailscale network, llama.cpp b11913
(rpc protocol version-locked across nodes):

```
host:      windows (DESKTOP-MEDRU5A)   llama-server  :8080, smollm2-135m gguf
rpc node 1: nixos (RTX 3060 box)       ggml-rpc-server :50052
rpc node 2: vps (ovh vps)              ggml-rpc-server :50052
tensor-split 2,2,1 across host + 2 rpc nodes
```

prompt: "Write one sentence describing what a swarm of machines pooling their
memory could do."

response (38 completion tokens):
> As a swarm of machines absorbs vast amounts of data and processes it in
> real-time, they could potentially unlock new insights and revolutionize
> business processes by facilitating more efficient data analysis and
> automation.

follow-up requests also succeeded (multi-turn stable). remote compute verified:
- vps rpc-server accumulated CPU time during the run (it computes its 1/5 share)
- earlier 2-node variant (nixos host + windows rpc node): killing the windows
  rpc-server mid-session broke inference — the remote node was load-bearing.

## binaries (no fetching needed)

the stick ships llama.cpp **b11913** release builds for all platforms in
`bin/`, and they already include the rpc pieces (`ggml-rpc-server`,
`ggml-rpc.dll` / `libggml-rpc.so`):
- windows x64: `bin/windows_x86_64/llama/` (extracted, ready to run)
- linux x64: `bin/linux_x86_64/llama-ubuntu-x64.tar.gz` → extract to get
  `llama-b11913/{llama-server,ggml-rpc-server}`
- provisioner (`provisioning/tools/download_internet_in_a_box.ps1`) already
  downloads these exact archives from ggml-org releases — the rpc binaries
  ride along inside them. audit entries for the rpc-server added to
  `provision_usb.sh` + `provisioning/lib/EngineStager.ps1` as a follow-up patch.

## operational notes (learned the hard way)

- ggml-rpc-server binds 127.0.0.1 by default — pass `--host 0.0.0.0` on every
  node or the host can't reach them across machines.
- ggml-rpc-server serves ONE client at a time. a wedged/crashed previous client
  leaves the server accepting nothing (backlog fills) — restart it, don't debug.
- start rpc-servers FIRST, then the llama-server host. if the host's model load
  hangs with zero rpc connections, a stale llama-server process from a previous
  attempt is usually still alive — `pkill -f llama-server` on every host.
- tensor-split weights are positional: host first, then rpc servers in the
  order listed in `--rpc`.
- keep `--rpc` endpoints on the same llama.cpp build (b11913 everywhere) — rpc
  protocol is version-locked.
- ports: ggml rpc default is 50052 which collides with the emyrge swarm node
  port; don't run both on the same machine at the same time (or move the swarm
  node port).
- windows: run the node/server in the foreground of a backgrounded ssh session
  (`ssh -f`). Start-Process/bat-file routes die silently.

## stop everything

- windows: `taskkill /F /IM llama-server.exe; taskkill /F /IM ggml-rpc-server.exe`
- nixos / vps: `pkill -f llama-server; pkill -f ggml-rpc-server`

## remaining scale question (not blocking)

all runs used smollm2-135m (105 MB). the plumbing works end to end; the next
step up is a tier-3-class model (qwen2.5-32b) where the 2,2,1-style split
across windows(16GB)+nixos(31GB+12GB vram) actually becomes necessary rather
than demonstrative. the stick carries qwen2.5-1.5b and Phi-3.5-mini as
intermediate steps.
