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
from dataclasses import dataclass
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
        except OSError as e:
            print(f"[WARN] Could not list {current}: {e}", file=sys.stderr)


def filter_paths(
    items: Iterable[RemoteItem],
    include_globs: list[str] | None = None,
    exclude_globs: list[str] | None = None,
    files_only: bool = True,
) -> list[RemoteItem]:
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
    p.parent.mkdir(parents=True, exist_ok=True)


def needs_download(local_path: Path, size: int) -> tuple[bool, int]:
    if not local_path.exists():
        return True, 0
    local_size = local_path.stat().st_size
    if local_size == size:
        return False, 0
    if local_size < size:
        return True, local_size
    return True, 0


def download_with_resume(
    host: str,
    port: int,
    username: str,
    password: str | None,
    key_filename: str | None,
    remote_path: str,
    local_path: Path,
    total_size: int,
    chunk_size: int = 1024 * 1024,
    timeout: int = 30,
) -> None:
    ssh, sftp = connect_sftp(host, port, username, password, key_filename, timeout=timeout)
    try:
        try:
            rstat = sftp.stat(remote_path)
            rsize = getattr(rstat, "st_size", 0)
        except OSError as e:
            raise RuntimeError(f"Remote missing: {remote_path} ({e})")

        should, offset = needs_download(local_path, rsize)
        if not should:
            return

        ensure_parent_dir(local_path)
        mode = "ab" if offset > 0 else "wb"

        with sftp.file(remote_path, "rb") as rf, open(local_path, mode) as lf:
            if offset > 0:
                rf.seek(offset)
            remaining = rsize - offset
            with tqdm(
                total=remaining,
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
                    pbar.update(len(data))

        if local_path.stat().st_size != rsize:
            raise RuntimeError(
                f"Incomplete download for {remote_path}: {local_path.stat().st_size} != {rsize}"
            )
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        try:
            ssh.close()
        except Exception:
            pass


def human_bytes(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def parse_years(spec: str) -> set[int]:
    """Parse "2008:2023", "2008-2015", "2008,2010,2012-2014" -> {years}"""
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
    """Build full-path glob patterns matching:
      {remote_root}/{year}/{var}_{year}_GLEAM_{version}.nc
    If vars_ is None -> any var.
    If years is None -> any year.
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
        print(f"[INFO] Listing remote: {remote_root} ...")
        items = list(_listdir_attr_recursive(sftp, remote_root))
    finally:
        try:
            sftp.close()
        except Exception:
            pass
        try:
            ssh.close()
        except Exception:
            pass

    files = filter_paths(items, include_globs=include_globs, exclude_globs=args.exclude, files_only=True)

    if not files:
        print("[INFO] No matching files found.")
        return

    total_bytes = sum(f.size for f in files)
    print(f"[INFO] Matched {len(files)} files, total size ~ {human_bytes(total_bytes)}")

    if args.list_only:
        for f in files:
            print(f"{f.path}  {human_bytes(f.size)}")
        return

    if args.dry_run:
        for f in files:
            rel = f.path.lstrip("/")
            print(f"[DRY RUN] Would download: {f.path} -> {dest_root / rel}")
        return

    futures = []
    lock = threading.Lock()
    with (
        tqdm(total=total_bytes, unit="B", unit_scale=True, unit_divisor=1024, desc="Total") as total_bar,
        ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex,
    ):

        def submit_download(fitem: RemoteItem):
            rel = fitem.path.lstrip("/")
            local = dest_root / rel
            should, _ = needs_download(local, fitem.size)
            if not should:
                return None

            def task():
                before = local.stat().st_size if local.exists() else 0
                download_with_resume(
                    host=args.host,
                    port=args.port,
                    username=args.username,
                    password=args.password,
                    key_filename=args.key_filename,
                    remote_path=fitem.path,
                    local_path=local,
                    total_size=fitem.size,
                )
                after = local.stat().st_size
                with lock:
                    total_bar.update(max(0, after - before))
                return local

            return ex.submit(task)

        for fitem in files:
            fut = submit_download(fitem)
            if fut is not None:
                futures.append(fut)

        for fut in as_completed(futures):
            try:
                res = fut.result()
                if res:
                    print(f"[OK] {res}")
            except Exception as e:
                print(f"[ERR] {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
