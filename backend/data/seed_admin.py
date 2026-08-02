"""
Standalone script to seed the demo admin account against whichever
database MONGODB_URI points to.

NOTE: if you're running the API locally WITHOUT MongoDB (MONGODB_URI
unset), you don't need this - app/main.py already seeds the admin
account automatically every time the API starts (see
app/admin_seed.py). This script is for the real-Mongo case: run it
once against your Atlas cluster (see docs/DEPLOYMENT.md) so the
account exists there too, since the API's auto-seed and this script
would otherwise be talking to two different databases.

Usage:
    cd backend
    ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=Something1! python -m data.seed_admin
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.admin_seed import ensure_admin_seeded  # noqa: E402

if __name__ == "__main__":
    ensure_admin_seeded()
