#!/usr/bin/env python3
"""
find_duplicates.py
------------------
Recursively scans your media volume, finds duplicate files by content hash,
shows you every group before touching anything, then asks for confirmation
before deleting.

Usage:
    python find_duplicates.py               # Full interactive run
    python find_duplicates.py --dry-run     # Report only, delete nothing
    python find_duplicates.py --auto        # Auto-keep the best path, no prompts
                                            #   (still shows a summary before deleting)

How duplicates are detected:
    1. Files with identical sizes are grouped (quick pre-filter).
    2. Each candidate group is hashed with SHA-256 — only files whose full
       hash matches are confirmed duplicates.  No false positives.

Which copy is kept (the "keeper"):
    Priority order (highest wins):
      1. File is inside a Season subdirectory        (properly organised)
      2. File lives deeper in the directory tree     (more organised)
      3. Longest filename                            (usually has more metadata)
      4. Alphabetical path                           (deterministic tiebreaker)

    The script never deletes ALL copies — at least one is always kept.

Requirements: Python 3.10+ standard library only.
"""

import argparse
import hashlib
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

LOCAL_MEDIA_ROOT = "Your Local Media Path"
# File extensions to scan.  Add/remove as needed.
SCAN_EXTENSIONS: set[str] = {
    ".mkv", ".mp4", ".avi", ".m4v", ".wmv",
    ".mov", ".ts", ".flv", ".webm",
}

# Chunk size used while hashing (4 MB)
HASH_CHUNK = 4 * 1024 * 1024

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("find_duplicates.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str | None:
    """Return the SHA-256 hex digest of a file, or None on read error."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            while chunk := fh.read(HASH_CHUNK):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        log.warning("Cannot read %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Keeper selection
# ---------------------------------------------------------------------------

import re as _re
_SEASON_RE = _re.compile(r'[Ss]eason\s*\d+')


def keeper_score(path: Path) -> tuple:
    """
    Higher score = more likely to be kept.
    Returns a tuple so paths are sorted descending (best first).
    """
    parts   = path.parts
    in_season = int(any(_SEASON_RE.search(p) for p in parts))   # 1 if in Season dir
    depth     = len(parts)                                        # deeper = more organised
    name_len  = len(path.name)                                    # longer name = richer metadata
    alpha     = path.as_posix().lower()                           # deterministic tiebreaker

    # We want highest score first → negate what should be larger
    return (in_season, depth, name_len, alpha)


def pick_keeper(paths: list[Path]) -> Path:
    """Return the path that should be kept (highest keeper_score)."""
    return sorted(paths, key=keeper_score, reverse=True)[0]


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def collect_files(root: Path) -> list[Path]:
    files = []
    for dirpath, _dirs, filenames in os.walk(root):
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in SCAN_EXTENSIONS and not fname.endswith(".part"):
                files.append(p)
    return files


def find_duplicate_groups(files: list[Path]) -> list[list[Path]]:
    """
    Return a list of groups; each group is a list of Paths that are
    byte-for-byte identical.  Groups with only one member are excluded.
    """
    log.info("Step 1/2 — grouping %d file(s) by size …", len(files))

    by_size: dict[int, list[Path]] = defaultdict(list)
    for p in files:
        try:
            by_size[p.stat().st_size].append(p)
        except OSError:
            pass

    candidates = [group for group in by_size.values() if len(group) > 1]
    candidate_count = sum(len(g) for g in candidates)
    log.info("  %d file(s) share a size with at least one other — hashing …",
             candidate_count)

    log.info("Step 2/2 — computing SHA-256 hashes …")
    by_hash: dict[str, list[Path]] = defaultdict(list)
    done = 0
    for group in candidates:
        for p in group:
            h = sha256_file(p)
            if h:
                by_hash[h].append(p)
            done += 1
            if done % 50 == 0:
                log.info("  Hashed %d / %d candidate file(s) …", done, candidate_count)

    duplicates = [sorted(group) for group in by_hash.values() if len(group) > 1]
    duplicates.sort(key=lambda g: g[0])   # stable display order
    return duplicates


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def print_group(idx: int, total: int, group: list[Path], keeper: Path, root: Path):
    size = keeper.stat().st_size
    print()
    print(f"  ┌─ Duplicate group {idx}/{total}  ({human_size(size)} each) {'─'*30}")
    for p in group:
        rel  = p.relative_to(root) if p.is_relative_to(root) else p
        tag  = "  KEEP  " if p == keeper else "  delete"
        print(f"  │  [{tag}]  {rel}")
    print(f"  └{'─'*60}")


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------

def delete_files(to_delete: list[Path], dry_run: bool) -> int:
    deleted = 0
    for p in to_delete:
        if dry_run:
            log.info("  [DRY-RUN] Would delete: %s", p)
        else:
            try:
                p.unlink()
                log.info("  Deleted: %s", p)
                deleted += 1
            except OSError as exc:
                log.error("  Could not delete %s: %s", p, exc)
    return deleted


# ---------------------------------------------------------------------------
# Interactive confirmation
# ---------------------------------------------------------------------------

def prompt_group(idx: int, total: int, group: list[Path], keeper: Path,
                 root: Path) -> list[Path] | None:
    """
    Show a duplicate group, ask the user what to do.
    Returns a list of paths to delete, or None to skip this group.
    """
    print_group(idx, total, group, keeper, root)
    to_delete = [p for p in group if p != keeper]

    while True:
        print()
        print("  Options:")
        print("    [y] Delete shown file(s), keep the suggested KEEP copy")
        print("    [c] Choose which copy to keep yourself")
        print("    [s] Skip this group — keep all copies")
        print("    [q] Quit (stop processing, keep everything remaining)")
        choice = input("  Your choice [y/c/s/q]: ").strip().lower()

        if choice == "y":
            return to_delete

        elif choice == "c":
            print()
            for i, p in enumerate(group):
                rel = p.relative_to(root) if p.is_relative_to(root) else p
                print(f"    [{i + 1}]  {rel}")
            while True:
                raw = input(
                    f"  Enter number to KEEP (1–{len(group)}), or 's' to skip: "
                ).strip()
                if raw.lower() == "s":
                    return None
                if raw.isdigit() and 1 <= int(raw) <= len(group):
                    chosen_keeper = group[int(raw) - 1]
                    return [p for p in group if p != chosen_keeper]
                print(f"  Please enter a number between 1 and {len(group)}, or 's'.")

        elif choice == "s":
            return None

        elif choice == "q":
            raise KeyboardInterrupt   # handled in main

        else:
            print("  Unrecognised input — please type y, c, s, or q.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate media files from your library."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report duplicates but do not delete anything.")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-select the best copy and delete the rest "
                             "after a single confirmation prompt.")
    args = parser.parse_args()

    root = Path(LOCAL_MEDIA_ROOT)
    if not root.is_dir():
        log.error("LOCAL_MEDIA_ROOT does not exist: %s", LOCAL_MEDIA_ROOT)
        sys.exit(1)

    if args.dry_run:
        print("=" * 62)
        print("  DRY-RUN MODE — nothing will be deleted")
        print("=" * 62)

    log.info("Scanning %s …", root)
    files = collect_files(root)
    log.info("Found %d video file(s) to check.", len(files))

    if not files:
        log.info("No files found. Check LOCAL_MEDIA_ROOT and SCAN_EXTENSIONS.")
        return

    groups = find_duplicate_groups(files)

    if not groups:
        log.info("✓ No duplicates found — library is clean!")
        return

    dup_file_count = sum(len(g) for g in groups)
    waste_bytes    = sum(
        g[0].stat().st_size * (len(g) - 1) for g in groups
    )
    print()
    print("=" * 62)
    print(f"  Found {len(groups)} duplicate group(s) across {dup_file_count} file(s).")
    print(f"  Potential space recovered: {human_size(waste_bytes)}")
    print("=" * 62)

    # ── Auto mode ──────────────────────────────────────────────────────────
    if args.auto or args.dry_run:
        all_to_delete: list[Path] = []
        for group in groups:
            keeper = pick_keeper(group)
            all_to_delete.extend(p for p in group if p != keeper)

        print()
        print("  Files that would be deleted:")
        for p in all_to_delete:
            rel = p.relative_to(root) if p.is_relative_to(root) else p
            print(f"    {rel}")
        print()

        if args.dry_run:
            log.info("DRY-RUN COMPLETE — %d file(s) would be deleted (%s recovered).",
                     len(all_to_delete), human_size(waste_bytes))
            return

        # auto mode — one global confirm
        ans = input(
            f"  Delete {len(all_to_delete)} file(s) automatically? [yes/no]: "
        ).strip().lower()
        if ans not in ("yes", "y"):
            log.info("Aborted — no files deleted.")
            return

        deleted = delete_files(all_to_delete, dry_run=False)
        log.info("Done — %d file(s) deleted.", deleted)
        log.info("Full log saved to find_duplicates.log")
        return

    # ── Interactive mode ───────────────────────────────────────────────────
    total_deleted = 0
    total_skipped = 0

    try:
        for i, group in enumerate(groups, start=1):
            keeper      = pick_keeper(group)
            to_delete   = prompt_group(i, len(groups), group, keeper, root)

            if to_delete is None:
                total_skipped += 1
                log.info("  Group %d/%d skipped.", i, len(groups))
                continue

            deleted = delete_files(to_delete, dry_run=False)
            total_deleted += deleted

    except KeyboardInterrupt:
        print()
        log.info("Stopped by user.")

    print()
    log.info("=" * 60)
    log.info("Session complete — %d file(s) deleted, %d group(s) skipped.",
             total_deleted, total_skipped)
    log.info("Full log saved to find_duplicates.log")


if __name__ == "__main__":
    main()
