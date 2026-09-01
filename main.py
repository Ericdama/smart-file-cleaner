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
from rich.columns import Columns
from rich.text import Text
import pyfiglet

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

def render_banner():
    """Renders an ASCII art header with styled panel borders."""
    banner_text = pyfiglet.figlet_format("SmartCleaner", font="slant")
    console.print(
        Panel(
            Text(banner_text, style="bold cyan"),
            subtitle="[bold white]v1.0.0 | High-Performance Duplicate & Artifact Cleaner[/bold white]",
            subtitle_align="right",
            border_style="magenta",
            expand=False
        )
    )

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

def get_file_type_badge(path: Path) -> str:
    """Returns a color-coded extension badge for visual scanning."""
    ext = path.suffix.lower()
    if ext in [".exe", ".msi", ".zip", ".tar", ".gz"]:
        return f"[bold red]{ext}[/bold red]"
    elif ext in [".pptx", ".docx", ".pdf", ".xlsx"]:
        return f"[bold blue]{ext}[/bold blue]"
    elif ext in [".mp4", ".mkv", ".avi", ".mp3"]:
        return f"[bold magenta]{ext}[/bold magenta]"
    elif ext in [".py", ".js", ".java", ".cpp", ".html"]:
        return f"[bold yellow]{ext}[/bold yellow]"
    return f"[dim]{ext if ext else 'file'}[/dim]"

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
    console.clear()
    render_banner()

    # --- Dashboard Cards ---
    card_path = Panel(
        f"[bold yellow]{target_path}[/bold yellow]", 
        title="[bold cyan]Target Path[/bold cyan]", 
        border_style="cyan"
    )
    card_size = Panel(
        f"[bold green]≥ {min_size_mb} MB[/bold green]", 
        title="[bold cyan]Min File Size[/bold cyan]", 
        border_style="cyan"
    )
    status_color = "green" if check_builds else "red"
    card_builds = Panel(
        f"[{status_color}]{check_builds}[/{status_color}]", 
        title="[bold cyan]Scan Build Artifacts[/bold cyan]", 
        border_style="cyan"
    )

    console.print(Columns([card_path, card_size, card_builds]))
    console.print()

    min_size_bytes = int(min_size_mb * 1024 * 1024)
    size_groups: Dict[int, List[Path]] = {}
    found_heavy_dirs: List[Tuple[Path, int]] = []

    # --- Step 1: Directory Walker ---
    with Progress(
        SpinnerColumn(spinner_name="dots"),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as progress:
        progress.add_task(description="[bold cyan]Scanning directory tree...", total=None)

        for root, dirs, files in os.walk(target_path):
            current_root = Path(root)

            if check_builds:
                for d in list(dirs):
                    if d in HEAVY_FOLDERS:
                        full_heavy_path = current_root / d
                        dir_size = sum(
                            f.stat().st_size for f in full_heavy_path.rglob('*') if f.is_file()
                        )
                        found_heavy_dirs.append((full_heavy_path, dir_size))
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
            SpinnerColumn(spinner_name="bouncingBar"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40, style="black", complete_style="bold green"),
            TaskProgressColumn(),
            console=console
        ) as progress:
            hash_task = progress.add_task("[bold cyan]Hashing size-matched candidates...", total=total_files_to_hash)

            for size, paths in candidate_size_groups.items():
                for path in paths:
                    file_hash = compute_stream_hash(path)
                    if file_hash:
                        duplicates.setdefault(file_hash, []).append(path)
                    progress.advance(hash_task)

    duplicate_sets = {h: paths for h, paths in duplicates.items() if len(paths) > 1}

    # --- Step 3: Render Results ---
    console.print("\n")
    
    # Render Heavy Directories Table
    if found_heavy_dirs:
        table_heavy = Table(
            title="📦 Heavy Build Artifacts Detected",
            header_style="bold magenta",
            box=None,
            show_lines=True
        )
        table_heavy.add_column("Artifact Directory Path", style="dim")
        table_heavy.add_column("Disk Footprint", justify="right", style="bold red")

        total_heavy_space = 0
        for path, size in found_heavy_dirs:
            table_heavy.add_row(str(path), format_bytes(size))
            total_heavy_space += size

        console.print(Panel(table_heavy, border_style="magenta"))
        console.print(f"[bold yellow]Total build artifact footprint:[/bold yellow] [bold red]{format_bytes(total_heavy_space)}[/bold red]\n")

    # Render Duplicates Table
    if duplicate_sets:
        table_dups = Table(
            title="👥 Duplicate Files Identified",
            header_style="bold cyan",
            show_lines=True
        )
        table_dups.add_column("Group", justify="center", style="bold green", width=10)
        table_dups.add_column("Type", justify="center", width=8)
        table_dups.add_column("File Path")
        table_dups.add_column("Size", justify="right", style="bold yellow", width=12)

        wasted_space = 0
        set_idx = 1
        for file_hash, paths in duplicate_sets.items():
            fsize = paths[0].stat().st_size
            wasted_space += fsize * (len(paths) - 1)
            
            for p in paths:
                table_dups.add_row(
                    f"Set #{set_idx}",
                    get_file_type_badge(p),
                    str(p),
                    format_bytes(fsize)
                )
            set_idx += 1

        console.print(Panel(table_dups, border_style="cyan"))
        console.print(f"[bold yellow]Total reclaimable duplicate space:[/bold yellow] [bold red]{format_bytes(wasted_space)}[/bold red]\n")
    else:
        console.print(Panel("[bold green]✓ No duplicate files detected above the size threshold.[/bold green]", border_style="green"))

    if not duplicate_sets and not found_heavy_dirs:
        return

    # --- Step 4: Interactive Cleanup Prompt ---
    confirm_clean = inquirer.confirm(
        message="Launch interactive cleanup process?",
        default=False
    ).execute()

    if confirm_clean:
        clean_interactive(duplicate_sets, found_heavy_dirs)

def clean_interactive(duplicate_sets: Dict[str, List[Path]], heavy_dirs: List[Tuple[Path, int]]):
    """Handles the interactive file and directory selection/deletion."""
    deleted_bytes = 0
    deleted_files_count = 0

    if heavy_dirs:
        choices = [{"name": f"{p} ({format_bytes(s)})", "value": (p, s)} for p, s in heavy_dirs]
        selected_dirs = inquirer.checkbox(
            message="Select heavy directories to REMOVE (Space to toggle, Enter to confirm):",
            choices=choices
        ).execute()

        for path, size in selected_dirs:
            try:
                shutil.rmtree(path)
                console.print(f"[bold red]✗ Deleted folder:[/bold red] {path}")
                deleted_bytes += size
                deleted_files_count += 1
            except Exception as e:
                console.print(f"[bold yellow]⚠️ Failed to delete {path}:[/bold yellow] {e}")

    if duplicate_sets:
        for file_hash, paths in duplicate_sets.items():
            console.print(f"\n[bold cyan]Duplicate Set (Size: {format_bytes(paths[0].stat().st_size)})[/bold cyan]")
            
            choices = [{"name": f"KEEP: {p}", "value": p} for p in paths]
            choices.append({"name": "SKIP THIS SET (Keep all)", "value": None})

            keep_path = inquirer.select(
                message="Select file to KEEP (others will be permanently deleted):",
                choices=choices
            ).execute()

            if keep_path is not None:
                for p in paths:
                    if p != keep_path:
                        try:
                            f_size = p.stat().st_size
                            p.unlink()
                            console.print(f"[bold red]✗ Deleted duplicate:[/bold red] {p}")
                            deleted_bytes += f_size
                            deleted_files_count += 1
                        except Exception as e:
                            console.print(f"[bold yellow]⚠️ Failed to delete {p}:[/bold yellow] {e}")

    # Final Execution Summary Card
    summary_text = (
        f"[bold white]Items Deleted:[/bold white] [bold yellow]{deleted_files_count}[/bold yellow]\n"
        f"[bold white]Disk Space Reclaimed:[/bold white] [bold green]{format_bytes(deleted_bytes)}[/bold green]"
    )
    console.print("\n")
    console.print(Panel(summary_text, title="[bold green]✓ Cleanup Complete[/bold green]", border_style="green", expand=False))

if __name__ == "__main__":
    app()