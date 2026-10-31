#!/usr/bin/env python3
"""Dumps every Xbox 360 shader container Shank (1) draws with, for Renut's translator (sa2_renderer = "renut").

Shank 1 keeps its effect files loose in data-360/bootstrap/shaders (*.fxc), each holding whole containers (Shank 2
had them in data-360/data-360.zip). Any .fxc inside a .zip of the game, and the loaded default.xex image
(out/default_image.bin, REXGLUE_DUMP_IMAGE during codegen: the movie player's and the UI library's built-in shaders)
are scanned too. Same container check and naming as sa2-nx's tools/sa2_dump_shaders.py (reNut's
tools/dump_shaders.py).

Output: <out>/{vs,ps}_<xxh3_64 of the container>.bin and <out>/manifest.csv.

  python tools/shank1_dump_shaders.py --game ../extracted --out out/renut_shader_dump
"""
import argparse
import csv
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sa2_dump_shaders import find_shader_headers  # noqa: E402  (also checks that xxhash is installed)
import xxhash  # noqa: E402


def sources(game, image):
    for dirpath, _, files in os.walk(game):
        for f in sorted(files):
            path = os.path.join(dirpath, f)
            rel = os.path.relpath(path, game).replace(os.sep, "/")
            if f.lower().endswith(".fxc"):
                with open(path, "rb") as fh:
                    yield rel, fh.read()
            elif f.lower().endswith(".zip"):
                with zipfile.ZipFile(path) as z:
                    for entry in sorted(n for n in z.namelist() if n.lower().endswith(".fxc")):
                        yield rel + ":" + entry, z.read(entry)
    if os.path.isfile(image):
        with open(image, "rb") as fh:
            yield "default.xex (image)", fh.read()
    else:
        print("warning: no %s: the executable's shaders are left out" % image)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10) * 2)[0])
    ap.add_argument("--game", default=os.path.join(root, "..", "extracted"),
                    help="the game folder (default.xex, data/, data-360/)")
    ap.add_argument("--image", default=os.path.join(root, "out", "default_image.bin"))
    ap.add_argument("--no-image", action="store_true", help="leave the executable's shaders out")
    ap.add_argument("--out", default=os.path.join(root, "out", "renut_shader_dump"))
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    seen = set()
    manifest = []
    for source, data in sources(args.game, "" if args.no_image else args.image):
        count = 0
        for h in find_shader_headers(data):
            flags, virt, phys = struct.unpack_from(">III", data, h)
            blob = data[h:h + virt + phys]
            kind = "vs" if flags & 1 else "ps"
            name = "%s_%s" % (kind, xxhash.xxh3_64_hexdigest(blob))
            manifest.append((name, kind, virt, phys, source, "0x%x" % h))
            count += 1
            if name in seen:
                continue
            seen.add(name)
            with open(os.path.join(args.out, name + ".bin"), "wb") as fh:
                fh.write(blob)
        if count:
            print("%-50s %4d shaders" % (source, count))
    manifest.sort()
    with open(os.path.join(args.out, "manifest.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "type", "virtual_size", "physical_size", "source", "offset"])
        w.writerows(manifest)
    ps = sum(1 for n in seen if n.startswith("ps_"))
    print("%d unique shaders (%d ps, %d vs) -> %s" % (len(seen), ps, len(seen) - ps, args.out))


if __name__ == "__main__":
    main()
