# Catefolio Local Development Notes

## Environment

- **Python Environment**: Use conda environment `catefolio`
  ```bash
  conda run -n catefolio <command>
  ```
- **Backend Port**: 8000 (default)
- **GCP Project**: relays-cloud

## Running the Backend

```bash
conda run -n catefolio uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Firestore Migration System

Custom migration system for Firestore located at `backend/migrations/`.

### Commands

```bash
# Check migration status
conda run -n catefolio python -m migrations.runner status

# Run pending migrations
conda run -n catefolio python -m migrations.runner migrate

# Create new migration
conda run -n catefolio python -m migrations.runner create <name>
```

### Migration File Naming

Migrations follow the pattern: `m_YYYYMMDD_NNN_description.py`

Example: `m_20260112_001_add_user_id.py`

### Migration Structure

Each migration has:
- `upgrade(db)`: Run the migration
- `downgrade(db)`: Reverse the migration (optional)

Executed migrations are tracked in `_migrations` Firestore collection.

---

## Firebase Services

### Firestore Collections

| Collection | Purpose | Key Fields |
|------------|---------|------------|
| `jobs` | Transaction processing jobs | `user_id`, `status`, `transaction_count`, `summary` |
| `jobs/{id}/transactions` | Individual transactions (sub-collection) | `date`, `description`, `amount`, `category` |
| `entities` | User-defined entities | `user_id`, `name`, `aliases`, `description` |
| `categories` | Expense categories | Document ID = `user_id` or `default` |
| `_migrations` | Migration tracking | `executed_at`, `status` |

**Data Structure:**
```
jobs/{job_id}
├── user_id, status, summary, charts, transaction_count
└── transactions/ (sub-collection)
    ├── 00000000: {date, description, amount, category, ...}
    ├── 00000001: {date, description, amount, category, ...}
    └── ...
```

### Cloud Storage

- **Bucket**: `{project_id}-uploads` (e.g., `relays-cloud-uploads`)
- **Path Structure**: `uploads/{user_id}/{filename}`
- Files are stored per-user with signed URLs for access

### Authentication

Firebase Auth with JWT token verification. Supports demo mode for testing.

**Protected Routes**: Use `get_current_user` dependency
```python
from app.auth.firebase_auth import FirebaseUser, get_current_user

@router.get("/protected")
def protected_route(user: FirebaseUser = Depends(get_current_user)):
    return {"user_id": user.uid}
```

**Optional Auth**: Use `get_optional_user` for public endpoints
```python
from app.auth.firebase_auth import FirebaseUser, get_optional_user

@router.get("/public")
def public_route(user: Optional[FirebaseUser] = Depends(get_optional_user)):
    if user:
        return {"user_id": user.uid}
    return {"message": "Anonymous access"}
```

### Demo Mode (for demopage)

Demo mode is enabled by default (`DEMO_MODE=true`). To use:

```bash
# Send X-Demo-User-Id header
curl -H "X-Demo-User-Id: my-session-id" http://localhost:8000/me

# Response:
# {
#   "uid": "demo_my-session-id",
#   "email": "my-session-id@demo.catefolio.local",
#   "name": "Demo User (my-session-id)",
#   "is_demo": true
# }
```

**Frontend usage**: Send `X-Demo-User-Id` header with a unique session ID (e.g., UUID or browser fingerprint) to identify demo users.

To disable demo mode in production:
```bash
export DEMO_MODE=false
```

---

## Multi-Tenant Architecture

All data is scoped by `user_id`:

```
User (Firebase Auth)
└── user_id (UID)
    ├── jobs/{job_id}         → User's transaction jobs
    ├── entities/{entity_id}  → User's custom entities
    ├── categories/{user_id}  → User's categories (falls back to "default")
    └── uploads/{user_id}/    → User's files in Cloud Storage
```

### Repository Methods

All repository methods accept optional `user_id` for multi-tenant filtering:

```python
# With user context (authenticated)
repo.save_job(job_id, payload, user_id=user.uid)
repo.load_job(job_id, user_id=user.uid)
repo.list_entities(user_id=user.uid)

# Without user context (backward compatibility / admin)
repo.save_job(job_id, payload)
repo.load_job(job_id)
repo.list_entities()
```

---

## Project Structure

```
backend/
├── app/
│   ├── api/routes.py           # API endpoints
│   ├── auth/
│   │   └── firebase_auth.py    # Firebase Auth middleware
│   ├── repositories/
│   │   ├── firestore_repo.py   # Firestore repository (primary)
│   │   └── local_repo.py       # Local file repository (legacy)
│   ├── storage/
│   │   └── cloud_storage.py    # Cloud Storage service
│   ├── services/               # Business logic
│   └── schemas/models.py       # Pydantic models
├── migrations/
│   ├── runner.py               # Migration runner
│   └── m_*.py                  # Migration scripts
└── requirements.txt
```
