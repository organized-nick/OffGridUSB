# Offline Content Catalog — Expansion (2026-11-04)

what changed: `manifests/zim.json` grew from 12 to 54 archives (+42), all
sourced from the live kiwix/openZIM catalog. per product direction, **all
content is available on all SKUs/tiers** — every new entry is `tier: 0` with
`required_for_skus` = Product1/Product2/Product3/Tier3/Tier4. the tier ladder
differentiates on the LLM + swarm stack, not on content.

## what's in the expansion

- **maps**: OSM country map zims (united-states 15.8GB, canada 10.4GB) —
  browsable in kiwix-serve like any other zim, zero new serving infra.
- **manuals / military pubs**: armypubs_en_all (7.9GB, US-gov public domain),
  FAS military-medicine reference.
- **engineering / appropriate tech**: cd3wd (541MB), appropedia maxi,
  energypedia, 100r.co (hundred rabbits), solar low-tech magazine.
- **medical**: medlineplus, mdwiki maxi, NHS medicines A-to-Z, CDC travelers'
  health, quick-guides-for-medicine.
- **prepper / community**: trueprepper, canadian-prepper bugout roll,
  urban prepper, S2 Underground, learning-self-reliance, ready.gov (EN+ES).
- **repair**: iFixit English (3.4GB), restarters wiki.
- **education**: libretexts (chem/phys/bio/med/k12), phet sims, wikiversity.
- **Q&A depth**: stackexchange zims — diy, electronics, outdoors, woodworking,
  mechanics, engineering, arduino, 3dprinting, gis.
- **software stack**: devdocs linux man pages.

full list w/ sizes + descriptions: see `manifests/zim.json`.

## provenance & integrity

- sizes come from download.kiwix.org/library/library_zim.xml (2026-11-04).
- sha256 for every new entry comes from the official `.zim.sha256` sidecar
  published next to each zim on the kiwix mirror — no download needed to pin.
- entries are `verified_local: false` until actually staged; fetch_assets.py
  verifies magic header + sha256 on download as before.

## extended catalog weight

the new archives total **~78.7 GiB**. combined with the existing catalog,
the full content set exceeds small-stick payloads (Product1 is an 8GB drive).
`products.json` payload profiles were intentionally left untouched — the
profiles still stage the original curated per-SKU lists; the expanded catalog
is fully resolvable by `fetch_assets.py --tier` and available to kiwix-serve
wherever staged. a future pass can either raise drive SKUs or add a
"content-complete" mega SKU. deliberately NOT added (too large for any USB
SKU): wikipedia maxi (110GB, already tier-gated), gutenberg_en_all (206GB),
survivorlibrary (205GB), khanacademy_en (168GB), world map all (74GB),
crashcourse (21.5GB).

## regenerating

`provisioning/tools/refresh_zim_catalog.py` re-fetches the live kiwix catalog
and appends any selection additions (idempotent on filenames, never touches
existing entries). edit the `SELECTION` list to grow the catalog.
