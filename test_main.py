import os
from pathlib import Path
import pytest
from main import compute_stream_hash, format_bytes, HEAVY_FOLDERS


# --- 1. Tests for Utility Functions ---

def test_format_bytes():
    """Verify byte formatting handles various magnitude tiers correctly."""
    assert format_bytes(500) == "500.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1048576) == "1.00 MB"
    assert format_bytes(1073741824) == "1.00 GB"


# --- 2. Tests for Stream Hashing ---

def test_compute_stream_hash_identical_content(tmp_path: Path):
    """Ensure identical file content produces matching SHA-256 hashes."""
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"

    content = b"Developer tooling tests content for duplicate hashing verification."
    file1.write_bytes(content)
    file2.write_bytes(content)

    hash1 = compute_stream_hash(file1)
    hash2 = compute_stream_hash(file2)

    assert hash1 != ""
    assert hash1 == hash2


def test_compute_stream_hash_different_content(tmp_path: Path):
    """Ensure different file contents yield distinct SHA-256 hashes."""
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"

    file1.write_bytes(b"Content A")
    file2.write_bytes(b"Content B")

    hash1 = compute_stream_hash(file1)
    hash2 = compute_stream_hash(file2)

    assert hash1 != hash2


def test_compute_stream_hash_missing_file(tmp_path: Path):
    """Verify graceful failure (empty string) when file does not exist."""
    non_existent_file = tmp_path / "ghost_file.bin"
    hash_result = compute_stream_hash(non_existent_file)
    assert hash_result == ""


# --- 3. Tests for 2-Pass Duplicate Detection Logic ---

def test_two_pass_duplicate_detection(tmp_path: Path):
    """
    Simulates the 2-pass detection algorithm:
    Pass 1: Group by byte size.
    Pass 2: Stream hash files with identical sizes.
    """
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    # Create two duplicate files (3000 bytes each)
    dup_data = b"X" * 3000
    file1 = dir_a / "dup1.dat"
    file2 = dir_b / "dup2.dat"
    file1.write_bytes(dup_data)
    file2.write_bytes(dup_data)

    # Create a unique file with the same size (3000 bytes) but different content
    file3 = dir_a / "unique_same_size.dat"
    file3.write_bytes(b"Y" * 3000)

    # Create a unique file with a completely different size (1000 bytes)
    file4 = dir_b / "unique_diff_size.dat"
    file4.write_bytes(b"Z" * 1000)

    # --- Pass 1: Size grouping ---
    size_groups = {}
    for p in tmp_path.rglob("*"):
        if p.is_file():
            size_groups.setdefault(p.stat().st_size, []).append(p)

    candidates = {s: paths for s, paths in size_groups.items() if len(paths) > 1}

    # Pass 1 assertion
    assert 1000 not in candidates
    assert 3000 in candidates
    assert len(candidates[3000]) == 3

    # --- Pass 2: Stream Hashing ---
    duplicates_map = {}
    for path in candidates[3000]:
        h = compute_stream_hash(path)
        duplicates_map.setdefault(h, []).append(path)

    duplicate_sets = {h: paths for h, paths in duplicates_map.items() if len(paths) > 1}

    # Pass 2 assertions
    assert len(duplicate_sets) == 1
    dup_paths = list(duplicate_sets.values())[0]
    assert len(dup_paths) == 2
    assert file1 in dup_paths
    assert file2 in dup_paths
    assert file3 not in dup_paths


# --- 4. Test Heavy Folder Identification ---

def test_heavy_folder_recognition():
    """Verify heavy build directory constants."""
    assert "node_modules" in HEAVY_FOLDERS
    assert "target" in HEAVY_FOLDERS
    assert "build" in HEAVY_FOLDERS
    assert ".venv" in HEAVY_FOLDERS