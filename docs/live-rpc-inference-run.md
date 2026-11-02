# live rpc pooled-inference run (2026-11-02)

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
