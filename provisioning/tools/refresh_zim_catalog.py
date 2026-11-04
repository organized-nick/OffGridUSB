#!/usr/bin/env python3
"""Regenerate/extend manifests/zim.json from the live kiwix library catalog.

Fetches https://download.kiwix.org/library/library_zim.xml, resolves a curated
selection of archives, pulls per-file sha256 from the official .zim.sha256
sidecars, and appends new entries to the manifest (existing entries untouched).

Per product direction (2026-11-04): all content is available to ALL tiers —
new entries are tier 0 with required_for_skus covering every SKU. The
differentiator between tiers is the LLM + swarm capability, not content.

Usage:
    python3 provisioning/tools/refresh_zim_catalog.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifests" / "zim.json"
LIB_URL = "https://download.kiwix.org/library/library_zim.xml"
BASE = "https://download.kiwix.org/zim/"

# (category subdir, filename, manifest id, display name, category tag, description)
SELECTION = [
    ("zimit", "armypubs_en_all_2024-12.zim", "armypubs-en-all",
     "US Army Publishing Directorate Field Manuals", "military_manuals",
     "US Army field manuals: survival (FM 3-05.70), first aid, mountaineering, rangers, etc. US-gov public domain."),
    ("zimit", "cd3wdproject.org_en_all_2025-11.zim", "cd3wd-en-all",
     "CD3WD Core Data for Development", "appropriate_technology",
     "Hundreds of technical engineering docs for low-resource settings: agriculture, water, construction, energy."),
    ("other", "appropedia_en_all_maxi_2026-02.zim", "appropedia-en-maxi",
     "Appropedia (Maxi)", "appropriate_technology",
     "Open wiki of appropriate technology, permaculture, off-grid infrastructure, and sustainability solutions."),
    ("other", "energypedia_en_all_nopic_2026-06.zim", "energypedia-en-nopic",
     "energypedia (No-Pic)", "appropriate_technology",
     "Community wiki on off-grid renewable energy, microgrids, solar PV design, and energy access."),
    ("zimit", "ready.gov_en_all_2026-10.zim", "readygov-en-all",
     "Ready.gov Emergency Preparedness (EN)", "emergency_prep",
     "FEMA preparedness guidance: disaster plans, go-bags, hazard-specific response. Public domain."),
    ("zimit", "ready.gov_es_all_2026-10.zim", "readygov-es-all",
     "Ready.gov Emergency Preparedness (ES)", "emergency_prep",
     "FEMA preparedness guidance, Spanish edition. Public domain."),
    ("zimit", "medlineplus.gov_en_all_2025-01.zim", "medlineplus-en-all",
     "MedlinePlus Medical Reference", "medical_first_aid",
     "US National Library of Medicine consumer health reference: conditions, drugs, procedures, tests."),
    ("other", "theworldfactbook_en_all_2026-02.zim", "worldfactbook-en-all",
     "CIA World Factbook", "situational_awareness",
     "Country profiles: geography, infrastructure, demographics, communications. US-gov public domain."),
    ("zimit", "irp.fas.org_en_military-medicine_2026-10.zim", "fas-military-medicine-en",
     "FAS Military Medicine & Warfare Reference", "military_manuals",
     "Federation of American Scientists military medicine and warfare reference library."),
    ("zimit", "nhs.uk_en_medicines_2026-09b.zim", "nhs-medicines-en",
     "NHS Medicines A to Z", "medical_first_aid",
     "UK National Health Service drug formulary: uses, doses, side effects for hundreds of medicines."),
    ("zimit", "wwwnc.cdc.gov_en_all_2024-11.zim", "cdc-travelers-health-en",
     "CDC Travelers' Health", "medical_first_aid",
     "CDC travel health notices, disease reference, vaccination guidance."),
    ("other", "mdwiki_en_all_maxi_2025-11.zim", "mdwiki-en-maxi",
     "MDWiki Medical Encyclopedia (Maxi)", "medical_first_aid",
     "Simplified medicine encyclopedia distilled from Wikipedia for austere clinical use."),
    ("videos", "quickguidesformedicine_en_all_2026-06.zim", "quickguides-medicine-en",
     "Quick Guides for Medicine (Surviving Residency)", "medical_first_aid",
     "Rapid clinical reference videos for frontline and austere medicine."),
    ("other", "trueprepper.com_en_all_2026-05.zim", "trueprepper-en-all",
     "TruePrepper Preparedness Archive", "prepper_community",
     "Preparedness guides: bug-out planning, stockpiling, SHTF scenarios, EDC."),
    ("videos", "canadian-prepper_en_bugoutroll_2026-10.zim", "canadian-prepper-bugoutroll-en",
     "Canadian Prepper — Bug-Out Roll", "prepper_community",
     "Video series on bug-out bag and loadout design for evacuation scenarios."),
    ("videos", "lrnselfreliance_en_all_2026-09.zim", "lrnselfreliance-en-all",
     "Learning Self-Reliance", "prepper_community",
     "Video channel on homesteading, bushcraft, food preservation, and self-reliance skills."),
    ("videos", "s2underground_en_all_2026-10.zim", "s2underground-en-all",
     "S2 Underground — Grid-Down Intelligence", "prepper_community",
     "Video series on grid-down infrastructure analysis, SHTF situational awareness, and preparedness intel."),
    ("videos", "urban-prepper_en_all_2026-08.zim", "urban-prepper-en-all",
     "Urban Prepper", "prepper_community",
     "Video series on apartment-scale prepping, storage food, and urban survival."),
    ("zimit", "100r.co_en_all_2026-08.zim", "100r-co-en-all",
     "Hundred Rabbits (100r.co)", "offgrid_living",
     "Off-grid sailing crew's documentation of low-power computing, solar setups, and passage-making."),
    ("zimit", "solar.lowtechmagazine.com_mul_all_2025-01.zim", "lowtech-solar-en",
     "Low-tech Magazine (Solar Edition)", "offgrid_living",
     "Solar-powered site covering low-energy technology, hand tools, and off-grid living design."),
    ("other", "restarters_en_all_maxi_2026-10.zim", "restarters-en-maxi",
     "Restarters Repair Wiki (Maxi)", "repair",
     "Community repair wiki: electronics, appliances, and device troubleshooting."),
    ("ifixit", "ifixit_en_all_2025-12.zim", "ifixit-en-all",
     "iFixit Repair Manuals (English)", "repair",
     "Tens of thousands of step-by-step device and hardware repair guides."),
    ("other", "openstreetmap-wiki_en_all_nopic_2026-10.zim", "osm-wiki-en-nopic",
     "OpenStreetMap Wiki (No-Pic)", "maps",
     "OSM project wiki: how mapping works, tagging, tools for offline map workflows."),
    ("maps", "maps_en_united-states-of-america_2026-06.zim", "maps-usa-en",
     "OSM Map: United States", "maps",
     "Full OpenStreetMap map of the USA with roads, landmarks and address data, browsable offline."),
    ("maps", "maps_en_canada_2026-06.zim", "maps-canada-en",
     "OSM Map: Canada", "maps",
     "Full OpenStreetMap map of Canada with roads, landmarks and address data, browsable offline."),
    ("stack_exchange", "diy.stackexchange.com_en_all_2026-10.zim", "se-diy-en-all",
     "Home Improvement Q&A", "stackexchange",
     "Stack Exchange Q&A archive: construction, plumbing, electrical, workshop practice."),
    ("stack_exchange", "electronics.stackexchange.com_en_all_2026-10.zim", "se-electronics-en-all",
     "Electronics Q&A", "stackexchange",
     "Stack Exchange Q&A archive: circuit design, repair, embedded electronics."),
    ("stack_exchange", "outdoors.stackexchange.com_en_all_2026-10.zim", "se-outdoors-en-all",
     "The Great Outdoors Q&A", "stackexchange",
     "Stack Exchange Q&A archive: backpacking, navigation, wilderness skills."),
    ("stack_exchange", "woodworking.stackexchange.com_en_all_2026-10.zim", "se-woodworking-en-all",
     "Woodworking Q&A", "stackexchange",
     "Stack Exchange Q&A archive: joinery, tool use, timber framing."),
    ("stack_exchange", "mechanics.stackexchange.com_en_all_2026-10.zim", "se-mechanics-en-all",
     "Motor Vehicle Mechanics Q&A", "stackexchange",
     "Stack Exchange Q&A archive: vehicle repair and diagnostics."),
    ("stack_exchange", "engineering.stackexchange.com_en_all_2026-10.zim", "se-engineering-en-all",
     "Engineering Q&A", "stackexchange",
     "Stack Exchange Q&A archive: general engineering practice."),
    ("stack_exchange", "arduino.stackexchange.com_en_all_2026-10.zim", "se-arduino-en-all",
     "Arduino Q&A", "stackexchange",
     "Stack Exchange Q&A archive: microcontrollers, sensors, DIY automation."),
    ("stack_exchange", "3dprinting.stackexchange.com_en_all_2026-10.zim", "se-3dprinting-en-all",
     "3D Printing Q&A", "stackexchange",
     "Stack Exchange Q&A archive: additive manufacturing and printer maintenance."),
    ("stack_exchange", "gis.stackexchange.com_en_all_2026-10.zim", "se-gis-en-all",
     "Geographic Information Systems Q&A", "stackexchange",
     "Stack Exchange Q&A archive: GIS, GPS, cartography, offline geodata workflows."),
    ("phet", "phet_en_all_2026-08.zim", "phet-en-all",
     "PhET Interactive Science Simulations", "education_stem",
     "University of Colorado physics/chemistry/biology/math interactive simulations."),
    ("wikiversity", "wikiversity_en_all_nopic_2026-11.zim", "wikiversity-en-nopic",
     "Wikiversity (No-Pic)", "education_stem",
     "Wikimedia open-learning community: courses, tutorials, research."),
    ("libretexts", "libretexts.org_en_chem_2025-01.zim", "libretexts-chem-en",
     "Chemistry LibreTexts", "education_stem",
     "Open-access chemistry textbook library."),
    ("libretexts", "libretexts.org_en_phys_2026-01.zim", "libretexts-phys-en",
     "Physics LibreTexts", "education_stem",
     "Open-access physics textbook library."),
    ("libretexts", "libretexts.org_en_bio_2025-01.zim", "libretexts-bio-en",
     "Biology LibreTexts", "education_stem",
     "Open-access biology textbook library."),
    ("libretexts", "libretexts.org_en_med_2025-01.zim", "libretexts-med-en",
     "Medicine LibreTexts", "education_stem",
     "Open-access anatomy/physiology/clinical textbook library."),
    ("libretexts", "libretexts.org_en_k12_2026-01.zim", "libretexts-k12-en",
     "K-12 Education LibreTexts", "education_stem",
     "Open-access K-12 textbook library."),
    ("devdocs", "devdocs_en_man_2026-10.zim", "devdocs-man-en",
     "Linux man Pages", "software_docs",
     "Offline Unix manual pages for the rebuild-the-software-stack angle."),
]

ALL_SKUS = ["Product1", "Product2", "Product3", "Tier3", "Tier4"]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "OffGridUSB-Provisioner/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with tempfile.NamedTemporaryFile(suffix=".xml") as tf:
        tf.write(fetch(LIB_URL))
        tf.flush()
        catalog = {b.attrib["path"]: b.attrib for b in ET.parse(tf.name).getroot().iter("book")}

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    existing_filenames = {a["filename"] for a in manifest["archives"]}
    added, total_new_bytes = [], 0

    for sub, fn, ident, name, cat, desc in SELECTION:
        path = f"/data/zim/{sub}/{fn}"
        if path not in catalog:
            print(f"MISSING in catalog: {path}", file=sys.stderr)
            return 1
        if fn in existing_filenames:
            print(f"skip (already in manifest): {fn}")
            continue
        meta = catalog[path]
        size_bytes = int(meta["size"]) * 1024
        sha_url = f"{BASE}{sub}/{fn}.sha256"
        sha256 = fetch(sha_url).decode().split()[0].strip().lower()
        entry = {
            "id": ident,
            "name": name,
            "filename": fn,
            "tier": 0,
            "category": cat,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / 1048576, 1),
            "sha256": sha256,
            "magic_header": "5A494D04",
            "verified_local": False,
            "required_for_skus": list(ALL_SKUS),
            "url": f"{BASE}{sub}/{fn}",
            "description": desc,
        }
        added.append(entry)
        total_new_bytes += size_bytes
        print(f"ok {ident:<30} {entry['size_mb']:>9.1f} MB  {sha256[:12]}")

    if not added:
        print("nothing to add")
        return 0
    print(f"\n{len(added)} new archives, {total_new_bytes / 1073741824:.2f} GiB additional catalog weight")
    if args.dry_run:
        print("(dry run, manifest unchanged)")
        return 0

    manifest["archives"].extend(added)
    manifest["description"] = manifest["description"].replace(
        "(Tiers 0-4)", "(Tiers 0-4, full content available on all SKUs)")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
