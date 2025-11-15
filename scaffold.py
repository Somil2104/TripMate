#!/usr/bin/env python3
from pathlib import Path

# Define directories to create
DIRS = [
    "app",
    "graph",
    "graph/prompts",
    "agents/planner",
    "agents/flights",
    "agents/hotels",
    "agents/activities",
    "agents/budget",
    "agents/intrip",
    "agents/common",
    "tools",
    "models",
    "services",
    "tests",
    "docs",
    "ui",
]

# Define empty files to create
FILES = [
    "README.md",
    "requirements.txt",
    ".env.example",
    ".gitignore",
    "app/api.py",
    "app/settings.py",
    "graph/supervisor.py",
    "graph/policies.py",
    "graph/state_store.py",
    "graph/prompts/supervisor.txt",
    "agents/planner/graph.py",
    "agents/flights/graph.py",
    "agents/hotels/graph.py",
    "agents/activities/graph.py",
    "agents/budget/graph.py",
    "agents/intrip/graph.py",
    "agents/common/__init__.py",
    "tools/flights.py",
    "tools/hotels.py",
    "tools/activities.py",
    "tools/weather.py",
    "tools/maps.py",
    "tools/translate.py",
    "tools/ocr.py",
    "tools/budget.py",
    "models/state.py",
    "models/flights.py",
    "models/hotels.py",
    "models/activities.py",
    "models/itinerary.py",
    "models/budget.py",
    "models/expense.py",
    "services/db.py",
    "services/cache.py",
    "services/logging.py",
    "services/observability.py",
    "tests/test_health.py",
    "docs/architecture.md",
    "docs/contracts.md",
    "docs/runbooks.md",
    "ui/README.md",
]

def main():
    root = Path.cwd()

    # Create directories
    for d in DIRS:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        print(f"dir: {p}")

    # Create empty files without overwriting existing ones
    for f in FILES:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.touch()
            print(f"file: {p}")
        else:
            print(f"skip (exists): {p}")

    # Minimal .gitignore if missing
    gi = root / ".gitignore"
    if gi.exists() and gi.stat().st_size == 0:
        gi.write_text(
            "__pycache__/\n.pytest_cache/\n.env\n.venv/\n.DS_Store\n.idea/\n.vscode/\n"
        )
        print("seeded .gitignore")

    print("Scaffold complete.")

if __name__ == "__main__":
    main()
