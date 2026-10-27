# ==============================================================================
# OffGridUSB (offgridusb.com) -- Tier 0 Pitch & Field Asset Stager
# Wrapper around download_internet_in_a_box.ps1 (-Tier 0 -NonInteractive)
# ==============================================================================

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "download_internet_in_a_box.ps1") -Tier 0 -NonInteractive @args
