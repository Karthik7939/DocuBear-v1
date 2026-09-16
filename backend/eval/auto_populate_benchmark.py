"""
eval/auto_populate_benchmark.py
--------------------------------
Automatically scans cloned git repositories (in `repositories/` or specified paths)
and populates `backend/eval/benchmark_dataset.json` with real commit SHAs,
commit descriptions, modified/added file lists, and relevance ground truth.

Usage:
------
  python backend/eval/auto_populate_benchmark.py \
      --repo-dir repositories/ \
      --max-commits 3 \
      --output backend/eval/benchmark_dataset.json
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure backend directory is in sys.path
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logger = logging.getLogger("eval.auto_populate")


def get_git_commits(repo_path: Path, max_commits: int = 3) -> list[dict[str, Any]]:
    """Extract recent commit metadata and diff file lists from a git repo."""
    if not (repo_path / ".git").exists():
        logger.warning(f"Not a git repository: {repo_path}")
        return []

    # Get recent commit hashes and subjects
    cmd = ["git", "-C", str(repo_path), "log", f"-n{max_commits}", "--format=%H|%s"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        logger.error(f"Git log failed for {repo_path}: {res.stderr}")
        return []

    lines = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
    commits: list[dict[str, Any]] = []

    for line in lines:
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        sha, msg = parts[0], parts[1]

        # Get changed files status for this commit
        diff_cmd = ["git", "-C", str(repo_path), "show", "--name-status", "--oneline", sha]
        diff_res = subprocess.run(diff_cmd, capture_output=True, text=True, check=False)

        added: list[str] = []
        modified: list[str] = []

        if diff_res.returncode == 0:
            diff_lines = diff_res.stdout.strip().split("\n")[1:]  # skip header line
            for dline in diff_lines:
                tokens = dline.strip().split("\t")
                if len(tokens) >= 2:
                    status, fpath = tokens[0], tokens[-1]
                    if status.startswith("A"):
                        added.append(fpath)
                    elif status.startswith("M") or status.startswith("R") or status.startswith("C"):
                        modified.append(fpath)

        ground_truth = list(dict.fromkeys(added + modified))
        scope = "small" if len(ground_truth) <= 2 else ("medium" if len(ground_truth) <= 5 else "large")

        commits.append({
            "commit_sha": sha,
            "scope": scope,
            "description": msg,
            "added_files": added,
            "modified_files": modified,
            "ground_truth_context_files": ground_truth,
            "relevance_type": "binary",
        })

    return commits


def populate_benchmark(
    repo_dir: Path,
    output_json: Path,
    max_commits: int = 3,
) -> Path:
    """Scan repos in repo_dir and update output_json with commit details."""
    repos_to_scan: list[Path] = []
    if repo_dir.is_dir():
        if (repo_dir / ".git").exists():
            repos_to_scan.append(repo_dir)
        else:
            for item in repo_dir.iterdir():
                if item.is_dir() and (item / ".git").exists():
                    repos_to_scan.append(item)

    if not repos_to_scan:
        logger.warning(f"No git repositories found in {repo_dir}")

    benchmark_repos = []
    for repo_path in repos_to_scan:
        repo_name = repo_path.name.replace("_", "/")
        commits = get_git_commits(repo_path, max_commits=max_commits)
        if commits:
            benchmark_repos.append({
                "repo_slug": repo_path.name,
                "repository_name": repo_name,
                "repository_path": str(repo_path).replace("\\", "/"),
                "language": "Python / TypeScript",
                "file_count": len(list(repo_path.glob("**/*"))),
                "test_commits": commits,
            })

    dataset = {
        "benchmark_repositories": benchmark_repos if benchmark_repos else [
            {
                "repo_slug": "Karthik7939_Mindstride-test-repo-v1",
                "repository_name": "Karthik7939/Mindstride-test-repo-v1",
                "repository_path": "backend/generated_docs/Karthik7939_Mindstride-test-repo-v1",
                "language": "Python / TypeScript",
                "test_commits": [],
            }
        ]
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    logger.info(f"Populated {len(benchmark_repos)} repositories into {output_json}")
    return output_json


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Auto-populate benchmark_dataset.json from git repositories")
    parser.add_argument("--repo-dir", type=str, default="repositories", help="Path to repositories directory or specific repo")
    parser.add_argument("--output", type=str, default="backend/eval/benchmark_dataset.json", help="Path to output JSON")
    parser.add_argument("--max-commits", type=int, default=3, help="Max commits to extract per repo")
    args = parser.parse_args()

    repo_path = Path(args.repo_dir).resolve()
    output_path = Path(args.output).resolve()

    print("=== DocAgent Auto-Populate Benchmark Dataset ===")
    print(f"Repository source: {repo_path}")
    print(f"Output path:       {output_path}")

    populate_benchmark(repo_path, output_path, max_commits=args.max_commits)
    print("SUCCESS: benchmark_dataset.json automatically populated!")


if __name__ == "__main__":
    main()
