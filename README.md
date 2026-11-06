find_duplicates

A cautious, dependency-free command-line tool that finds byte-for-byte duplicate video files in a media library (built with Jellyfin / Plex / Kodi-style TV folders in mind), shows you every duplicate group, and only deletes after you confirm.

No false positives: files are confirmed duplicates only when their full SHA-256 hashes match.
Safe by default: nothing is deleted without an explicit prompt, and --dry-run guarantees nothing is touched.
Never deletes every copy: each group always keeps at least one file.
Zero dependencies: Python standard library only.

⚠️ Deletion is permanent. Files are removed with Path.unlink(). There is no recycle bin and no undo. Always run --dry-run first and keep backups of anything you can't replace. See Safety.

Details
Content-based detection	Size pre-filter, then full-file SHA-256 on candidates only
Three run modes	Interactive (per-group prompts), --auto (one global confirmation), --dry-run (report only)
Suggested keeper	Deterministic scoring that prefers organized Season N folders
Manual override	Choose which copy to keep for any group
Audit trail	Everything is logged to the console and to find_duplicates.log
Space estimate	Reports potential space recovered before you commit to anything
Cross-platform	Windows, Linux, macOS
Requirements
Python 3.10 or newer (the script uses X | None type syntax)
No third-party packages

Check your version:

bash
python --version
Installation
bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>

There is nothing to install. The tool is a single file: find_duplicates.py.

Configuration

Open find_duplicates.py and edit the CONFIG section near the top.

python
LOCAL_MEDIA_ROOT = "Your Local Media Path"

SCAN_EXTENSIONS: set[str] = {
    ".mkv", ".mp4", ".avi", ".m4v", ".wmv",
    ".mov", ".ts", ".flv", ".webm",
}

HASH_CHUNK = 4 * 1024 * 1024  # 4 MB
Setting	Purpose
LOCAL_MEDIA_ROOT	Folder to scan recursively. You must change this before the first run.
SCAN_EXTENSIONS	Lowercase file extensions to consider. Add or remove entries as needed.
HASH_CHUNK	Read size used while hashing. 4 MB is a good default; rarely needs changing.

Path examples

python
# Windows (use a raw string so backslashes are not treated as escapes)
LOCAL_MEDIA_ROOT = r"D:\Media\TV"

# Linux / macOS
LOCAL_MEDIA_ROOT = "/mnt/media/TV"

Files ending in .part (incomplete downloads) are always skipped.

Usage
bash
python find_duplicates.py              # Interactive: review and confirm each group
python find_duplicates.py --dry-run    # Report only: deletes nothing
python find_duplicates.py --auto       # Auto-pick keepers, one global confirmation
Flag	Behavior
(none)	Interactive mode. You are prompted for every duplicate group.
--dry-run	Scans, hashes, and lists exactly what would be deleted. Never deletes. Takes precedence over --auto if both are given.
--auto	Picks the suggested keeper for every group, prints the full deletion list, then asks a single yes/no question before deleting.
Recommended workflow
Back up anything irreplaceable.
Run python find_duplicates.py --dry-run and read the report.
Run in interactive mode for the first real cleanup so you can inspect each group.
Use --auto only once you trust the keeper rules for your library layout.
Trigger a library rescan in your media server afterwards.
Interactive prompt options

For each duplicate group you can choose:

Key	Action
y	Delete the files marked delete, keep the suggested KEEP copy
c	Choose which copy to keep yourself (enter its number, or s to skip)
s	Skip this group and keep all copies
q	Quit immediately; everything not yet processed is kept

Deletion in interactive mode happens per group, immediately after you confirm it. Quitting midway does not undo groups you already approved.

Example output
text
14:02:11  INFO      Scanning /mnt/media/TV …
14:02:13  INFO      Found 4812 video file(s) to check.
14:02:13  INFO      Step 1/2 — grouping 4812 file(s) by size …
14:02:13  INFO        37 file(s) share a size with at least one other — hashing …
14:02:13  INFO      Step 2/2 — computing SHA-256 hashes …

==============================================================
  Found 18 duplicate group(s) across 37 file(s).
  Potential space recovered: 42.7 GB
==============================================================

  ┌─ Duplicate group 1/18  (1.4 GB each) ──────────────────────────────
  │  [  KEEP  ]  Example Show/Season 2/Example Show - S02E04 - Pilot.mkv
  │  [  delete]  Example Show/Example Show - S02E04.mkv
  └────────────────────────────────────────────────────────────

  Options:
    [y] Delete shown file(s), keep the suggested KEEP copy
    [c] Choose which copy to keep yourself
    [s] Skip this group — keep all copies
    [q] Quit (stop processing, keep everything remaining)
  Your choice [y/c/s/q]:
How it works
Collect: walk LOCAL_MEDIA_ROOT recursively and gather files whose extension is in SCAN_EXTENSIONS (excluding .part).
Size pre-filter: group files by size in bytes. A file with a unique size cannot have a duplicate, so it is never read. This avoids hashing most of a typical library.
Hash candidates: compute a full-file SHA-256 (streamed in HASH_CHUNK pieces, so memory use stays flat even for very large files) for files that share a size.
Group: files with identical hashes form a duplicate group.
Choose a keeper for each group (see below), present the results, and delete only what you confirm.

Because detection uses a full cryptographic hash, a match means the files are identical byte for byte.

How the "keeper" is chosen

Within each group the script ranks files and suggests the highest-ranked one. Criteria are applied in order:

Priority	Rule	Rationale
1	Path contains a Season <number> folder (case-insensitive on the S)	Properly organized
2	Deeper in the directory tree	More organized
3	Longer filename	Usually carries more metadata (title, quality tags)
4	Alphabetical path	Deterministic tiebreaker

These rules are heuristics. They are a suggestion, not a guarantee that the keeper is the copy you would pick. In interactive mode you can override any group with c.

Safety
Permanent deletion. There is no trash or undo. Treat y and yes as final.
Dry run first. --dry-run is the only mode with a hard guarantee that nothing is deleted.
At least one copy survives. Every group retains its keeper (or your chosen copy).
Review before --auto. Auto mode trusts the heuristics for the entire library, so read the printed deletion list before answering yes.
Scope your scan. Point LOCAL_MEDIA_ROOT at the narrowest folder that makes sense (for example, just TV) rather than a whole drive.
Mind your tooling. If a download client, torrent client, or media manager is still using the files (for example, actively seeding), deleting copies can break it. Pause those tools or exclude those folders first.
Back up. The best safety net is one you set up before running a delete tool.
Known limitations
Hardlinks are reported as duplicates. Hardlinked files share the same data on disk and hash identically. Deleting one frees no space, and the "potential space recovered" figure will be overstated for libraries that use hardlinks (common with *arr-style download setups).
Symlinks are followed. A symlink and its target can be grouped together as "duplicates."
Empty files. Zero-byte files with a video extension all share the same size and hash, so they are reported as duplicates of each other.
Exact matches only. Re-encodes, different resolutions, remuxes, or files with altered metadata are not detected, because their bytes differ.
No exclusions. There is no built-in ignore list for folders or filename patterns.
Hash time scales with data. On large libraries or network shares, the hashing step can take a long time. Progress is logged every 50 files.
Keeper rules assume Season N naming. Libraries organized differently may see less useful suggestions.
Troubleshooting
Symptom	Likely cause and fix
LOCAL_MEDIA_ROOT does not exist	The path is still the placeholder or is mistyped. Edit the CONFIG section. On Windows, use a raw string (r"...").
No files found	Wrong folder, or your files use an extension that is not in SCAN_EXTENSIONS.
Cannot read <file> warnings	Permission problem, locked file, or a disconnected drive. The file is skipped and not considered for deletion.
Could not delete <file> errors	The file is open in another program or you lack write permission. Close the program or fix permissions, then re-run.
Very slow run	Large files or a network drive. Run against a narrower folder, or run locally on the machine that owns the disk.
Python syntax error on launch	You are on Python older than 3.10. Upgrade Python.
FAQ

Does it compare filenames? No. Detection is purely content-based. Filenames only influence which copy is suggested as the keeper.

Will it ever delete all copies of a file? No. Each group always retains one file.

Can it send files to the recycle bin instead? Not currently. Deletion is permanent. A pull request adding trash support (for example via send2trash) would be welcome, though it would break the "no dependencies" property unless made optional.

Where is the log? find_duplicates.log is created in the directory you run the script from, and new runs are appended to it. It contains full file paths and media titles, so don't share or commit it.

Is it safe to run on a live media server? It only reads files until you confirm a deletion, but hashing generates heavy disk I/O. Run it during quiet hours, and rescan your library afterwards.

Contributing

Contributions are welcome.

Open an issue describing the bug or feature before large changes.
Fork the repo and create a feature branch.
Keep the tool dependency-free where possible and compatible with Python 3.10+.
Test with --dry-run against a throwaway directory containing known duplicates, including a hardlink, a symlink, and a zero-byte file.
Open a pull request describing what changed and why.

Ideas on the roadmap: hardlink and symlink awareness, folder/pattern exclusions, optional trash support, and a CLI argument for the scan path.

License

Add a LICENSE file to the repository and reference it here (for example, MIT).

Disclaimer

This software is provided "as is", without warranty of any kind. You are responsible for verifying what it proposes to delete. The authors are not liable for data loss.
