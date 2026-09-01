import hashlib
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import typer
from InquirerPy import inquirer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

app = typer.Typer(
    help="⚡ Smart CLI File Cleaner & Duplicate Finder",
    add_completion=False
)
console = Console()

# Folders commonly associated with unused build artifacts
HEAVY_FOLDERS = {
    "node_modules", "target", "dist", "build", ".next", 
    ".cache", "__pycache__", "venv", ".venv"
}

def format_bytes(size: int) -> str:
    """Formats bytes into human-readable strings."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"

def compute_stream_hash(file_path: Path, chunk_size: int = 65536) -> str:
    """Streams file contents in chunks to compute SHA-256 without memory overload."""
    hasher = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError):
        return ""

@app.command()
def scan(
    target_path: Path = typer.Option(
        Path("."),
        "--path", "-p",
        help="Target directory path to scan.",
        exists=True, file_okay=False, dir_okay=True, readable=True, resolve_path=True
    ),
    min_size_mb: float = typer.Option(
        1.0,
        "--min-size", "-s",
        help="Minimum file size in MB to check for duplicates."
    ),
    check_builds: bool = typer.Option(
        True,
        "--check-builds/--no-builds",
        help="Include heavy developer build directories (node_modules, target, etc.)."
    )
):
    """
    🔍 Scans a directory for duplicate files and heavy build artifacts.
    """
    console.print(Panel.fit(
        f"[bold cyan]Scanning Directory:[/bold cyan] [yellow]{target_path}[/yellow]\n"
        f"[bold cyan]Min File Size:[/bold cyan] {min_size_mb} MB",
        title="[bold green]Smart Cleaner[/bold green]"
    ))

    min_size_bytes = int(min_size_mb * 1024 * 1024)
    size_groups: Dict[int, List[Path]] = {}
    found_heavy_dirs: List[Tuple[Path, int]] = []

    # --- Step 1: Directory Walker ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True
    ) as progress:
        progress.add_task(description="Walking file tree...", total=None)

        for root, dirs, files in os.walk(target_path):
            current_root = Path(root)

            # Detect heavy build folders
            if check_builds:
                for d in list(dirs):
                    if d in HEAVY_FOLDERS:
                        full_heavy_path = current_root / d
                        # Calculate folder size
                        dir_size = sum(
                            f.stat().st_size for f in full_heavy_path.rglob('*') if f.is_file()
                        )
                        found_heavy_dirs.append((full_heavy_path, dir_size))
                        # Don't recurse into this directory for duplicate scanning
                        dirs.remove(d)

            for file in files:
                file_path = current_root / file
                try:
                    if not file_path.is_symlink():
                        st_size = file_path.stat().st_size
                        if st_size >= min_size_bytes:
                            size_groups.setdefault(st_size, []).append(file_path)
                except (PermissionError, OSError):
                    continue

    # --- Step 2: Hashing Duplicates (2-Pass) ---
    candidate_size_groups = {size: paths for size, paths in size_groups.items() if len(paths) > 1}
    total_files_to_hash = sum(len(paths) for paths in candidate_size_groups.values())

    duplicates: Dict[str, List[Path]] = {}
    
    if total_files_to_hash > 0:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            hash_task = progress.add_task("[cyan]Hashing size-matched candidates...", total=total_files_to_hash)

            for size, paths in candidate_size_groups.items():
                for path in paths:
                    file_hash = compute_stream_hash(path)
                    if file_hash:
                        duplicates.setdefault(file_hash, []).append(path)
                    progress.advance(hash_task)

    # Filter hash maps to only keep true duplicates
    duplicate_sets = {h: paths for h, paths in duplicates.items() if len(paths) > 1}

    # --- Step 3: Render Results ---
    console.print("\n")
    
    # Render Heavy Directories Table
    if found_heavy_dirs:
        table_heavy = Table(title="📦 Heavy Artifact Directories Found", header_style="bold magenta")
        table_heavy.add_column("Path", style="dim")
        table_heavy.add_column("Size", justify="right", style="bold red")

        total_heavy_space = 0
        for path, size in found_heavy_dirs:
            table_heavy.add_row(str(path), format_bytes(size))
            total_heavy_space += size

        console.print(table_heavy)
        console.print(f"[bold yellow]Total build artifact space:[/bold yellow] [bold red]{format_bytes(total_heavy_space)}[/bold red]\n")

    # Render Duplicates Table
    if duplicate_sets:
        table_dups = Table(title="👥 Duplicate Files Found", header_style="bold cyan")
        table_dups.add_column("Set", justify="center", style="bold green")
        table_dups.add_column("File Path")
        table_dups.add_column("File Size", justify="right", style="bold yellow")

        wasted_space = 0
        set_idx = 1
        for file_hash, paths in duplicate_sets.items():
            fsize = paths[0].stat().st_size
            wasted_space += fsize * (len(paths) - 1)
            
            for p in paths:
                table_dups.add_row(f"Set #{set_idx}", str(p), format_bytes(fsize))
            set_idx += 1

        console.print(table_dups)
        console.print(f"[bold yellow]Total reclaimable duplicate space:[/bold yellow] [bold red]{format_bytes(wasted_space)}[/bold red]\n")
    else:
        console.print("[bold green]No duplicate files found above minimum size threshold![/bold green]\n")

    # Exit if nothing to clean up
    if not duplicate_sets and not found_heavy_dirs:
        return

    # --- Step 4: Interactive Cleanup Prompt ---
    confirm_clean = inquirer.confirm(
        message="Do you want to launch the interactive cleanup process?",
        default=False
    ).execute()

    if confirm_clean:
        clean_interactive(duplicate_sets, found_heavy_dirs)

def clean_interactive(duplicate_sets: Dict[str, List[Path]], heavy_dirs: List[Tuple[Path, int]]):
    """Handles the interactive file and directory selection/deletion."""
    deleted_bytes = 0

    # 1. Heavy Folder Deletion
    if heavy_dirs:
        choices = [{"name": f"{p} ({format_bytes(s)})", "value": (p, s)} for p, s in heavy_dirs]
        selected_dirs = inquirer.checkbox(
            message="Select heavy directories to REMOVE completely (Space to select, Enter to confirm):",
            choices=choices
        ).execute()

        for path, size in selected_dirs:
            try:
                shutil.rmtree(path)
                console.print(f"[bold red]Deleted folder:[/bold red] {path}")
                deleted_bytes += size
            except Exception as e:
                console.print(f"[bold yellow]Failed to delete {path}:[/bold yellow] {e}")

    # 2. Duplicate File Deletion
    if duplicate_sets:
        for file_hash, paths in duplicate_sets.items():
            console.print(f"\n[bold cyan]Duplicate Set (Size: {format_bytes(paths[0].stat().st_size)})[/bold cyan]")
            
            choices = [{"name": f"KEEP: {p}", "value": p} for p in paths]
            choices.append({"name": "SKIP THIS SET (Keep all)", "value": None})

            keep_path = inquirer.select(
                message="Choose WHICH file to KEEP (the unselected ones will be deleted):",
                choices=choices
            ).execute()

            if keep_path is not None:
                for p in paths:
                    if p != keep_path:
                        try:
                            f_size = p.stat().st_size
                            p.unlink()
                            console.print(f"[bold red]Deleted duplicate:[/bold red] {p}")
                            deleted_bytes += f_size
                        except Exception as e:
                            console.print(f"[bold yellow]Failed to delete {p}:[/bold yellow] {e}")

    console.print(Panel.fit(
        f"[bold green]Cleanup Complete![/bold green]\n"
        f"Total Space Reclaimed: [bold red]{format_bytes(deleted_bytes)}[/bold red]",
        title="[bold green]Success[/bold green]"
    ))

if __name__ == "__main__":
    app()