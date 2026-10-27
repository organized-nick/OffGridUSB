# OffGridUSB Manifests & Product Catalog System

This directory houses the master catalog descriptors and dynamic SKU specifications for OffGridUSB:

## Manifest Index
- **`products.json`**: Master SKU catalog defining products (Product 1: PocketSurvival, Product 2: FieldReady, Product 3: CivilizationArk, Tier 3: SwarmCluster, Tier 4: SettlementHub), cumulative tier mappings, payload sizes, drive requirements, and active/hidden feature flags.
- **`zim.json`**: Master OpenZIM knowledge catalog with exact metadata, categories, sizes, checksums, and Kiwix URLs across Tiers 0–4.
- **`models.json`**: Master GGUF quantized model catalog with exact metadata, architectures, quantization profiles, context window lengths, RAM requirements, checksums, and Hugging Face URLs across Tiers 0–4.
- **`product_sku.json`**: The active USB runtime descriptor placed on provisioned USB drives. Informs the Command Center server (`GET /api/status`) and web UI of active branding, active features, active models, active ZIM archives, and hidden UI tabs.
