#!/usr/bin/env python3
"""
LibraryXmlBuilder.py - Dynamic Kiwix library.xml builder for staged ZIM files.
Extracts book definitions matching physically present .zim files on the target USB.
"""

import os
import sys
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def build_library_xml(zim_dir: Path, template_xml: Path, output_xml: Path) -> int:
    """
    Scans zim_dir for *.zim files and builds a new library.xml containing
    only book tags matching physically present ZIM archives.
    """
    if not zim_dir.exists():
        raise FileNotFoundError(f"ZIM directory not found: {zim_dir}")
    if not template_xml.exists():
        raise FileNotFoundError(f"Template library.xml not found: {template_xml}")

    present_zims = {f.name.lower(): f for f in zim_dir.glob("*.zim")}
    
    tree = ET.parse(template_xml)
    root = tree.getroot()

    # Create new library element
    new_root = ET.Element("library", attrib=root.attrib)

    included_count = 0
    for book in root.findall("book"):
        path_attr = book.get("path", "")
        zim_filename = Path(path_attr).name.lower()
        if zim_filename in present_zims:
            new_root.append(book)
            included_count += 1

    output_xml.parent.mkdir(parents=True, exist_ok=True)
    new_tree = ET.ElementTree(new_root)
    ET.indent(new_tree, space="  ")
    new_tree.write(output_xml, encoding="utf-8", xml_declaration=True)

    return included_count


def main():
    parser = argparse.ArgumentParser(description="Kiwix library.xml builder for staged ZIMs")
    parser.add_argument("--zim-dir", required=True, help="Directory containing staged .zim files")
    parser.add_argument("--template", required=True, help="Template library.xml with full book metadata")
    parser.add_argument("--output", required=True, help="Output library.xml path")

    args = parser.parse_args()
    count = build_library_xml(Path(args.zim_dir), Path(args.template), Path(args.output))
    print(f"Generated {args.output} with {count} active ZIM archives.")


if __name__ == "__main__":
    main()
