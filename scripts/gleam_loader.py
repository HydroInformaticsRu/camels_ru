#!/usr/bin/env python3
"""GLEAM SFTP downloader (Paramiko) — with year/frequency/variable selectors.

Additions
- --version (e.g., v4.2a), --freq (daily|monthly)
- --years selector: "2008:2023", "2008-2015", or "2008,2010,2012-2014"
- --vars filter: variable short names (E, Et, Es, SMs, SMrz, S, Ep, Ep_rad, Ep_aero, Ew, Eb, Ei, H)
- Auto-builds include globs like:
  /data/v4.2a/daily/2019/E_2019_GLEAM_v4.2a.nc

Other features retained
- Recursive listing, resume, progress bars, parallel workers.
- Mirrors remote directory structure locally.

Security note
- Uses AutoAddPolicy for host keys by default; harden in production.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
import fnmatch
import getpass
import os
from pathlib import Path
import re
import stat
import sys
import threading

import paramiko
from tqdm import tqdm

sys.path.append(str(Path(__file__).parent.parent))
from src.utils.logger import setup_logger

logger = setup_logger("gleam_loader", log_file="logs/gleam_loader.log")


@dataclass
class RemoteItem:
    path: str
    size: int
    mtime: int
    is_dir: bool


def connect_sftp(
    host: str,
    port: int,
    username: str,
    password: str | None = None,
    key_filename: str | None = None,
    timeout: int = 30,
) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    """Establish an SSH/SFTP session and return both handles."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=username,
        password=password,
        key_filename=key_filename,
        timeout=timeout,
        look_for_keys=False,
        allow_agent=False,
        banner_timeout=timeout,
        auth_timeout=timeout,
    )
    return client, client.open_sftp()


def _listdir_attr_recursive(sftp: paramiko.SFTPClient, base: str) -> Iterable[RemoteItem]:
    """Yield `RemoteItem` entries by recursively walking the remote directory tree."""
    stack = [base]
    while stack:
        current = stack.pop()
        try:
            for entry in sftp.listdir_attr(current):
                name = entry.filename
                if name in (".", ".."):
                    continue
                full_path = f"{current.rstrip('/')}/{name}"
                mode = entry.st_mode
                is_dir = stat.S_ISDIR(mode)
                yield RemoteItem(
                    path=full_path,
                    size=getattr(entry, "st_size", 0),
                    mtime=getattr(entry, "st_mtime", 0),
                    is_dir=is_dir,
                )
                if is_dir:
                    stack.append(full_path)
        except OSError:
            logger.exception("Could not list remote directory: %s", current)


def filter_paths(
    items: Iterable[RemoteItem],
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    files_only: bool = True,
) -> list[RemoteItem]:
    """Filter remote items using include/exclude glob patterns."""
    include_globs = include_globs or ["*"]
    exclude_globs = exclude_globs or []
    filtered: list[RemoteItem] = []
    for it in items:
        if files_only and it.is_dir:
            continue
        if any(fnmatch.fnmatch(it.path, pat) for pat in include_globs):
            if not any(fnmatch.fnmatch(it.path, pat) for pat in exclude_globs):
                filtered.append(it)
    return filtered


def ensure_parent_dir(p: Path) -> None:
    """Ensure the parent directory of `p` exists."""
    p.parent.mkdir(parents=True, exist_ok=True)


class LocalFileState(str, Enum):
    MISSING = "missing"
    COMPLETE = "complete"
    PARTIAL = "partial"
    OVERSIZED = "oversized"


def inspect_local_file(local_path: Path, expected_size: int) -> LocalFileState:
    """Classify a local file status relative to the expected size."""
    try:
        local_size = local_path.stat().st_size
    except FileNotFoundError:
        return LocalFileState.MISSING
    except OSError as exc:
        logger.warning("Could not stat %s: %s", local_path, exc)
        return LocalFileState.MISSING

    if local_size == expected_size:
        return LocalFileState.COMPLETE
    if local_size < expected_size:
        return LocalFileState.PARTIAL
    return LocalFileState.OVERSIZED


def prepare_local_target(local_path: Path, state: LocalFileState) -> None:
    """Prepare a local target by deleting partial/oversized artifacts."""
    if state in (LocalFileState.PARTIAL, LocalFileState.OVERSIZED):
        removed_bytes: int | None = None
        try:
            removed_bytes = local_path.stat().st_size
        except FileNotFoundError:
            removed_bytes = None
        except OSError as exc:
            logger.warning("Could not stat incomplete local copy %s: %s", local_path, exc)
        try:
            local_path.unlink()
            if removed_bytes is not None:
                logger.warning(
                    "Removed incomplete local copy: %s (~ %s, state=%s)",
                    local_path,
                    human_bytes(removed_bytes),
                    state.value,
                )
            else:
                logger.warning("Removed incomplete local copy: %s (state=%s)", local_path, state.value)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise RuntimeError(f"Failed to remove {local_path}: {exc}") from exc
    ensure_parent_dir(local_path)


def download_file(
    host: str,
    port: int,
    username: str,
    password: str | None,
    key_filename: str | None,
    remote_path: str,
    local_path: Path,
    expected_size: int,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
) -> int:
    """Download a remote file to `local_path`, returning bytes written.

    Raises:
        RuntimeError: If the remote file cannot be read or the transfer ends with
            an unexpected byte count. Lower-level exceptions are logged and then
            re-raised for the caller to decide how to proceed.
    """
    ssh, sftp = connect_sftp(host, port, username, password, key_filename, timeout=timeout)
    try:
        try:
            rstat = sftp.stat(remote_path)
            rsize = getattr(rstat, "st_size", 0)
        except OSError as e:
            logger.exception("Remote missing or inaccessible: %s", remote_path)
            raise RuntimeError(f"Remote missing: {remote_path} ({e})") from e

        if expected_size and expected_size != rsize:
            logger.warning(
                "Remote size for %s changed from listing (%s -> %s)", remote_path, expected_size, rsize
            )

        temp_path = local_path.with_suffix(local_path.suffix + ".part")
        with suppress(FileNotFoundError):
            temp_path.unlink()

        ensure_parent_dir(temp_path)

        downloaded = 0
        try:
            with sftp.file(remote_path, "rb") as rf, open(temp_path, "wb") as lf:
                with tqdm(
                    total=rsize,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    leave=False,
                    desc=f"{Path(remote_path).name}",
                ) as pbar:
                    while True:
                        data = rf.read(chunk_size)
                        if not data:
                            break
                        lf.write(data)
                        bytes_read = len(data)
                        downloaded += bytes_read
                        pbar.update(bytes_read)
        except Exception:
            logger.exception("Failure while streaming %s", remote_path)
            with suppress(FileNotFoundError):
                temp_path.unlink()
            raise

        final_size = temp_path.stat().st_size
        if final_size != rsize:
            with suppress(FileNotFoundError):
                temp_path.unlink()
            logger.error(
                "Incomplete download for %s: wrote %s bytes, expected %s",
                remote_path,
                final_size,
                rsize,
            )
            raise RuntimeError(f"Incomplete download for {remote_path}: {final_size} != {rsize}")

        with suppress(FileNotFoundError):
            local_path.unlink()
        temp_path.replace(local_path)
        logger.info("Downloaded %s -> %s (%s bytes)", remote_path, local_path, final_size)
        return downloaded
    finally:
        try:
            sftp.close()
        except Exception as exc:
            logger.debug("Error closing SFTP client in download_file: %s", exc, exc_info=True)
        try:
            ssh.close()
        except Exception as exc:
            logger.debug("Error closing SSH client in download_file: %s", exc, exc_info=True)


def human_bytes(n: int) -> str:
    """Convert a byte count into a compact human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def parse_years(spec: str) -> set[int]:
    """Parse "2008:2023", "2008-2015", "2008,2010,2012-2014" -> {years}."""
    spec = spec.strip()
    years: set[int] = set()
    for part in re.split(r"\s*,\s*", spec):
        if not part:
            continue
        if ":" in part:
            a, b = part.split(":", 1)
        elif "-" in part:
            a, b = part.split("-", 1)
        else:
            years.add(int(part))
            continue
        years.update(range(int(a), int(b) + 1))
    return years


def build_include_globs(
    remote_root: str, version: str, freq: str, years: set[int] | None, vars_: list[str] | None
) -> list[str]:
    """Build glob patterns to match remote GLEAM files based on selectors.

    The function generates a list of remote path glob patterns using the provided
    remote root, GLEAM version, frequency (kept for API clarity), an optional set
    of years, and an optional list of variable short names. Patterns are produced
    to match filenames like:
      /data/v4.2a/daily/2019/E_2019_GLEAM_v4.2a.nc

    Parameters
    ----------
    remote_root : str
        Base remote directory (e.g. "/data/v4.2a/daily").
    version : str
        GLEAM version string (e.g. "v4.2a").
    freq : str
        Frequency string ("daily" or "monthly") — currently not used in pattern
        composition but kept for clarity and future use.
    years : set[int] | None
        If provided, restrict patterns to the given years.
    vars_ : list[str] | None
        If provided, restrict patterns to these variable short names (e.g. "E",
        "Ep_rad", "SMs").

    Returns:
    -------
    list[str]
        A list of glob patterns for matching remote files; each pattern includes
        both ".nc" and ".nc4" variants where applicable.
    """
    remote_root = remote_root.rstrip("/")
    patterns: list[str] = []

    if years:
        if vars_:
            for y in sorted(years):
                for v in vars_:
                    # exact var (supports Ep, Ep_rad, Ep_aero, etc.)
                    patterns.append(f"{remote_root}/{y}/{v}_{y}_GLEAM_{version}.nc")
        else:
            for y in sorted(years):
                patterns.append(f"{remote_root}/{y}/*_{y}_GLEAM_{version}.nc")
    else:
        # No year filter
        if vars_:
            for v in vars_:
                patterns.append(f"{remote_root}/*/{v}_*_GLEAM_{version}.nc")
        else:
            patterns.append(f"{remote_root}/*/*_GLEAM_{version}.nc")

    # Accept both .nc and .nc4 just in case
    patterns_with_ext = []
    for p in patterns:
        patterns_with_ext.append(p)
        if p.endswith(".nc"):
            patterns_with_ext.append(p + "4")
    return patterns_with_ext


def main():
    """Command-line entry point orchestrating the GLEAM download workflow."""
    import argparse

    parser = argparse.ArgumentParser(description="Download GLEAM data via SFTP.")

    # Connection
    parser.add_argument("--host", default="hydras.ugent.be")
    parser.add_argument("--port", type=int, default=2225)
    parser.add_argument("--username", default="gleamuser")
    parser.add_argument("--password", default=os.getenv("GLEAM_SFTP_PASSWORD"))
    parser.add_argument("--key", dest="key_filename", default=None)

    # GLEAM selectors
    parser.add_argument("--version", default="v4.2a", help="GLEAM version, e.g. v4.2a")
    parser.add_argument("--freq", choices=["daily", "monthly"], default="daily")
    parser.add_argument("--years", default=None, help='e.g. "2008:2023" or "2008,2010,2012-2014"')
    parser.add_argument(
        "--vars",
        nargs="*",
        default=None,
        help="Vars to include (e.g., E Et Es SMs SMrz S Ep Ep_rad Ep_aero Ew Eb Ei H). Default: all.",
    )

    # Advanced
    parser.add_argument(
        "--remote",
        default=None,
        help="Override remote base (default: /data/{version}/{freq}).",
    )
    parser.add_argument("--dest", default="./gleam_data", help="Local destination.")
    parser.add_argument("--exclude", nargs="*", default=[], help="Extra glob excludes.")
    parser.add_argument("--list-only", action="store_true", help="Only list matches.")
    parser.add_argument("--workers", type=int, default=2, help="Parallel download workers.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be downloaded.")
    args = parser.parse_args()

    if not args.password and not args.key_filename:
        args.password = getpass.getpass("SFTP password: ")

    # Compute default remote root from selectors
    remote_root = args.remote or f"/data/{args.version}/{args.freq}"

    # Build include patterns from selectors (if years/vars given)
    years: set[int] | None = parse_years(args.years) if args.years else None
    include_globs = build_include_globs(
        remote_root=remote_root, version=args.version, freq=args.freq, years=years, vars_=args.vars
    )

    dest_root = Path(args.dest).resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    # One control connection to list
    ssh, sftp = connect_sftp(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        key_filename=args.key_filename,
    )
    try:
        logger.info("Listing remote path: %s", remote_root)
        items = list(_listdir_attr_recursive(sftp, remote_root))
    finally:
        try:
            sftp.close()
        except Exception as exc:
            logger.debug(
                "Error closing SFTP client after listing %s: %s", remote_root, exc, exc_info=True
            )
        try:
            ssh.close()
        except Exception as exc:
            logger.debug(
                "Error closing SSH client after listing %s: %s", remote_root, exc, exc_info=True
            )

    files = filter_paths(items, include_globs=include_globs, exclude_globs=args.exclude, files_only=True)

    if not files:
        logger.info("No matching files found for %s", remote_root)
        return

    total_bytes = sum(f.size for f in files)
    logger.info("Matched %s files (~ %s)", len(files), human_bytes(total_bytes))

    state_map: dict[str, tuple[LocalFileState, Path]] = {}
    already_complete: list[tuple[RemoteItem, Path]] = []
    pending: list[tuple[RemoteItem, Path, LocalFileState]] = []

    for f in files:
        rel = f.path.lstrip("/")
        local = dest_root / rel
        state = inspect_local_file(local, f.size)
        state_map[f.path] = (state, local)
        if state == LocalFileState.COMPLETE:
            already_complete.append((f, local))
        else:
            pending.append((f, local, state))

    if already_complete:
        existing_bytes = sum(f.size for f, _ in already_complete)
        logger.info(
            "Already downloaded: %s files (~ %s)",
            len(already_complete),
            human_bytes(existing_bytes),
        )
    else:
        existing_bytes = 0

    remaining_bytes = sum(f.size for f, _, _ in pending)
    if pending:
        logger.info(
            "Pending downloads: %s files (~ %s)",
            len(pending),
            human_bytes(remaining_bytes),
        )

    if args.list_only:
        for f in files:
            logger.info("%s  %s", f.path, human_bytes(f.size))
        return

    if args.dry_run:
        for f in files:
            state, local = state_map[f.path]
            if state == LocalFileState.COMPLETE:
                action = "skip (already complete)"
            elif state == LocalFileState.MISSING:
                action = "download"
            else:
                action = f"re-download ({state.value})"
            logger.info("[DRY RUN] %s: %s -> %s", action, f.path, local)
        return

    if not pending:
        logger.info("All files already present locally.")
        return

    for _, local, state in pending:
        prepare_local_target(local, state)

    futures = []
    future_to_item: dict = {}
    lock = threading.Lock()
    with (
        tqdm(
            total=remaining_bytes,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc="Remaining",
        ) as total_bar,
        ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex,
    ):

        def submit_download(fitem: RemoteItem, local: Path):
            def task():
                downloaded = download_file(
                    host=args.host,
                    port=args.port,
                    username=args.username,
                    password=args.password,
                    key_filename=args.key_filename,
                    remote_path=fitem.path,
                    local_path=local,
                    expected_size=fitem.size,
                )
                with lock:
                    total_bar.update(downloaded)
                return local

            return ex.submit(task)

        for fitem, local, _ in pending:
            future = submit_download(fitem, local)
            futures.append(future)
            future_to_item[future] = (fitem.path, local)

        for fut in as_completed(futures):
            try:
                res = fut.result()
                if res:
                    logger.info("Completed download: %s", res)
            except Exception:
                remote_path, local_path = future_to_item.get(fut, ("<unknown>", "<unknown>"))
                logger.exception("Download failed for %s -> %s", remote_path, local_path)


if __name__ == "__main__":
    main()
