"""Command line: python -m sdg_india <command>

  fetch [--refresh]     download every official source into data/raw (cached; retries on failure)
  import <folder>       import official files downloaded elsewhere (e.g. with curl or a browser)
  build                 rebuild data/processed from data/raw, validate, and write the coverage manifest
  all [--refresh]       fetch (falling back to cached raw files if offline) and build
  site                  write the static website data (docs/data) from data/processed
  report                print the coverage manifest
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import build, config, geo, site
from .http import DownloadError, write_meta
from .sources import aspirational, mospi, mpi, niti, un_sdg
from .validate import ValidationError


def fetch(refresh: bool) -> dict:
    results = {}
    steps = [("UN SDG API (India, all pages)", lambda: un_sdg.fetch(refresh)),
             ("NITI Aayog SDG India Index 2023-24", lambda: niti.fetch(refresh)),
             ("MoSPI NIF Progress Report 2025", lambda: mospi.fetch(refresh)),
             ("NITI Aayog National MPI 2023 (district tables)", lambda: mpi.fetch(refresh)),
             ("NITI Aayog Aspirational Districts list", lambda: aspirational.fetch(refresh)),
             ("DataMeet state boundaries", lambda: geo.build(refresh))]
    for name, step in steps:
        try:
            step()
            results[name] = "ok"
        except (DownloadError, un_sdg.IncompleteDownload, OSError) as e:
            results[name] = f"FAILED: {e}"
        print(f"{name}: {results[name]}")
    return results


def import_folder(folder: Path) -> None:
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")
    pages = un_sdg.import_files(folder)
    print(f"UN SDG files imported: {len(pages)}")
    for pdf in folder.glob("*.pdf"):
        name = pdf.name.lower()
        if "multidim" in name or "mpi" in name:
            dest, url = mpi.PDF, mpi.URL
        elif "aspirational" in name:
            dest, url = aspirational.PDF, aspirational.URL
        elif "niti" in name or "india_index" in name:
            dest, url = niti.PDF, config.SOURCE_BY_ID[niti.SOURCE_ID]["url"]
        elif "mospi" in name or "nif" in name:
            dest, url = mospi.PDF, config.SOURCE_BY_ID[mospi.SOURCE_ID]["url"]
        else:
            print(f"  skipped {pdf.name} (not a known source)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, dest)
        write_meta(dest, url, 200, note=f"Downloaded outside the pipeline and imported from '{pdf.name}'.")
        print(f"  imported {pdf.name} -> {dest.relative_to(config.ROOT)}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m sdg_india", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--refresh", action="store_true", help="download again even if cached")
    sp = sub.add_parser("import")
    sp.add_argument("folder", type=Path)
    sub.add_parser("build")
    sub.add_parser("site", help="write the static website data (docs/data) from data/processed")
    sub.add_parser("report")
    args = p.parse_args(argv)

    if args.cmd in ("fetch", "all"):
        fetch(args.refresh)
    if args.cmd == "import":
        import_folder(args.folder)
    if args.cmd in ("build", "all", "import"):
        try:
            manifest = build.build()
        except ValidationError as e:
            print(f"VALIDATION FAILED: {e}")
            return 1
        print(json.dumps({"totals": manifest["totals"], "source_status": manifest["source_status"],
                          "validation": manifest["validation"]}, indent=2, default=str))
        print("website data:", site.build_site())
    if args.cmd == "site":
        print("website data:", site.build_site())
    if args.cmd == "report":
        f = config.PROCESSED / "manifest.json"
        print(f.read_text(encoding="utf-8") if f.exists() else "No build yet. Run `python -m sdg_india build`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
