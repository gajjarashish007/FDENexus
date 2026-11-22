"""Configuration for the M01 Self-Service Portal.

Everything is environment-driven with safe defaults so the module runs locally
with zero setup. No secrets are hard-coded for production use.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("M01_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite database path (platform metadata: users, requests, approvals, audit...)
DB_PATH = Path(os.environ.get("M01_DB_PATH", DATA_DIR / "m01.db"))

# JWT signing. MUST be overridden in any real deployment.
JWT_SECRET = os.environ.get("JWT_SECRET", "m01-dev-secret-change-me-please-32b+")
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "12"))

# First-run bootstrap admin (created only if there are no users yet).
BOOTSTRAP_ADMIN_USER = os.environ.get("M01_ADMIN_USER", "admin")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("M01_ADMIN_PASSWORD", "admin")
BOOTSTRAP_ADMIN_EMAIL = os.environ.get("M01_ADMIN_EMAIL", "admin@example.com")

# Server
HOST = os.environ.get("M01_HOST", "0.0.0.0")
PORT = int(os.environ.get("M01_PORT", "5001"))

# Demo mode: when true, infrastructure actions are SIMULATED (no real AWS call).
# Default ON for local use; set M01_DEMO=0 in production once real backends exist.
DEMO_MODE = os.environ.get("M01_DEMO", "1") != "0"
# Read live data from connected AWS accounts even in simulation mode. Reads never change anything;
# M01_DEMO only decides whether CHANGES are simulated. Set M01_LIVE_READS=0 for a fully offline demo.
LIVE_READS = os.environ.get("M01_LIVE_READS", "1") != "0"

# Seed demo resources/notifications on a fresh database. Default OFF: a fresh
# production install starts with an empty inventory. Set M01_SEED_DEMO=1 for a
# populated local demo.
SEED_DEMO = os.environ.get("M01_SEED_DEMO", "0") == "1"

# Production guard: refuse to start with the dev JWT secret or default admin
# password unless M01_ALLOW_INSECURE=1 (local only).
ALLOW_INSECURE = os.environ.get("M01_ALLOW_INSECURE", "1") == "1"

# Optional AWS region hint for display only.
# Default AWS region: used only when an AWS account has no region of its own.
# Each connected account carries its own region; that one wins for anything done in the account.
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
AWS_REGION_SOURCE = ("AWS_REGION" if os.environ.get("AWS_REGION") else
                     "AWS_DEFAULT_REGION" if os.environ.get("AWS_DEFAULT_REGION") else "built-in default")

# Password policy
PASSWORD_MIN_LENGTH = 8

# Roles recognized by the portal and their rank (higher = more access).
ROLES = {
    "viewer": 1,
    "developer": 2,
    "operator": 3,
    "approver": 3,
    "security": 3,
    "admin": 9,
}
DEFAULT_ROLE = "developer"
