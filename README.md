# ⚡ Smart CLI File Cleaner & Duplicate Finder

A high-performance Command Line Interface (CLI) tool built with Python, **Typer**, **Rich**, and **InquirerPy**. It scans target directories to identify duplicate files and reclaim disk space from heavy developer build artifacts (such as `node_modules`, `target`, or `.venv`).

---

## 🚀 Key Features

* **Two-Pass Hashing Strategy:** Groups candidate files by byte size first, then performs streaming SHA-256 hashing to eliminate unnecessary disk I/O and avoid out-of-memory errors on large files.
* **Heavy Directory Scanner:** Detects and reports bulky developer build artifacts (`node_modules`, `build`, `target`, `.venv`, etc.).
* **Interactive Terminal UI:** Built-in table formatting, live progress bars, and an interactive menu to safely choose which files to retain or delete.
* **Fully Unit-Tested:** Comprehensive suite powered by `pytest` verifying utility methods, hash accuracy, and edge cases.

---

## 🛠️ Setup & Installation

### 1. Clone & Navigate
```bash
git clone [https://github.com/Ericdama/smart-file-cleaner.git](https://github.com/Ericdama/smart-file-cleaner.git)
cd smart-file-cleaner

2. Set Up Virtual Environment & Dependencies
DOS
python -m venv venv
.\venv\Scripts\activate
pip install typer rich inquirerpy pytest
💻 How to Run
Basic Duplicate Scan
Scan a directory (e.g., Downloads) for duplicate files larger than 1.0 MB:

DOS
python main.py --path C:\Users\ERIC\Downloads --min-size 1.0
Scan Workspace for Build Artifacts
Include heavy build directories alongside duplicate checking:

DOS
python main.py --path C:\Users\ERIC\Documents\Projects --check-builds
Display Available Arguments
DOS
python main.py --help

🧪 Running Unit Tests
Run the unit test suite:

DOS
pytest -v