# Firestore Migrations
#
# This module provides a simple migration system for Firestore.
# Migrations are versioned Python scripts that transform data.
#
# Usage:
#   conda run -n catefolio python -m migrations.runner migrate
#   conda run -n catefolio python -m migrations.runner status
#   conda run -n catefolio python -m migrations.runner create <name>
