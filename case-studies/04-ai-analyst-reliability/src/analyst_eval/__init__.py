"""Evaluation harness for case study 04: is context a measurable intervention for AI analysts?"""

from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = CASE_DIR.parents[1]
DATA_DIR = CASE_DIR / "data"
DB_PATH = DATA_DIR / "analyst.db"
HOLDOUT_DB_PATH = DATA_DIR / "analyst_holdout.db"
CONTEXT_DIR = CASE_DIR / "context"
SKILLS_DIR = CASE_DIR / "skills"
QUESTIONS_DIR = CASE_DIR / "questions"
RUNS_DIR = CASE_DIR / "runs"
RESULTS_DIR = CASE_DIR / "results"
