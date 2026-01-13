# Catefolio Deployment Plan

## Overview
Deploy the demo service with:
- **Backend (API)**: Google Cloud Run (relays-cloud project) - production only
- **Frontend (Demo)**: Vercel (staging + production)
- **CI/CD**: GitHub Actions
- **Versioning**: Separate tags (`api-v1.x.x` / `web-v1.x.x`)

---

## CI/CD Trigger Summary

| Trigger | Backend CI | Frontend CI |
|---------|------------|-------------|
| Push to `main` (backend/**) | Run tests only | - |
| Push to `main` (web/**) | - | Deploy to Vercel staging |
| Tag `api-v*` | Deploy to Cloud Run | - |
| Tag `web-v*` | - | Deploy to Vercel production |

---

## Phase 1: Prerequisites & GCP Setup

### 1.1 Enable GCP APIs
```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com iam.googleapis.com \
  --project=relays-cloud
```

### 1.2 Create Artifact Registry
```bash
gcloud artifacts repositories create catefolio \
  --repository-format=docker \
  --location=us-central1 \
  --project=relays-cloud
```

### 1.3 Setup Workload Identity Federation for GitHub Actions
Create service account and configure OIDC authentication for keyless deployment.

---

## Phase 2: Backend Deployment

### 2.1 Update CORS (backend/app/main.py)
Add environment-based CORS configuration:
```python
import os
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
CORS_ORIGINS = {
    "development": [
        "http://localhost:5173", "http://localhost:5174",
        "http://localhost:5175", "http://localhost:5176",
        "http://127.0.0.1:5173", "http://127.0.0.1:5174",
        "http://127.0.0.1:5175", "http://127.0.0.1:5176",
    ],
    "production": [
        "https://catefolio-web.vercel.app",
        "https://catefolio-web-staging.vercel.app",
        # Vercel preview deployments
    ],
}
origins = CORS_ORIGINS.get(ENVIRONMENT, CORS_ORIGINS["development"])
```

### 2.2 Create GitHub Actions Workflow
**File**: `.github/workflows/backend-ci.yml`

- Push to `main` (backend/**) → Run tests
- Tag `api-v*` → Run tests + deploy to Cloud Run

### 2.3 Cloud Run Service

| Service Name | Region | Memory | Min/Max Instances |
|--------------|--------|--------|-------------------|
| `catefolio-api` | us-central1 | 1Gi | 0/100 |

**Environment Variables**:
- `GOOGLE_CLOUD_PROJECT=relays-cloud`
- `VERTEX_LOCATION=us-central1`
- `DEMO_MODE=true`
- `ENVIRONMENT=production`

---

## Phase 3: Frontend Deployment

### 3.1 Fix react-grab dependency (web/package.json)
Change from local file to npm package:
```diff
- "react-grab": "file:../../react-grab/packages/react-grab"
+ "react-grab": "^0.0.98"
```

### 3.2 Create Vercel config (web/vercel.json)
```json
{
  "framework": "vite",
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

### 3.3 Create GitHub Actions Workflow
**File**: `.github/workflows/frontend-ci.yml`

- Push to `main` (web/**) → Lint, build, deploy to Vercel staging
- Tag `web-v*` → Deploy to Vercel production

### 3.4 Vercel Environment Variables
- **Preview (Staging)**: `VITE_API_BASE=https://catefolio-api-xxx.run.app`
- **Production**: `VITE_API_BASE=https://catefolio-api-xxx.run.app`

(Both point to same production API)

---

## Phase 4: Release Scripts

### 4.1 Create deploy script (scripts/run_deploy.sh)
Interactive script to create release tags:
```bash
./scripts/run_deploy.sh api 1.0.0   # Creates api-v1.0.0
./scripts/run_deploy.sh web 1.0.0   # Creates web-v1.0.0
```

---

## Phase 5: GitHub Secrets Setup

| Secret | Purpose |
|--------|---------|
| `WIF_PROVIDER` | Workload Identity Federation provider |
| `WIF_SERVICE_ACCOUNT` | GCP service account for deployments |
| `VERCEL_TOKEN` | Vercel deployment authorization |
| `VERCEL_ORG_ID` | Vercel organization |
| `VERCEL_PROJECT_ID` | Vercel project |
| `PRODUCTION_API_URL` | Cloud Run production URL |
| `SLACK_WEBHOOK_URL` | (Optional) Deployment notifications |

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/main.py` | Modify | Environment-based CORS |
| `web/package.json` | Modify | Change react-grab to npm |
| `web/vercel.json` | Create | Vercel SPA routing config |
| `.github/workflows/backend-ci.yml` | Create | Backend CI/CD |
| `.github/workflows/frontend-ci.yml` | Create | Frontend CI/CD |
| `scripts/run_deploy.sh` | Create | Release tag creation script |

---

## Release Workflow

```
1. Develop on feature branches
2. PR to main
   - Backend changes: tests run automatically
   - Frontend changes: auto-deploy to Vercel staging
3. QA frontend on staging (uses production API)
4. When ready: ./scripts/run_deploy.sh <component> <version>
5. GitHub Actions deploys to production
6. Slack notification confirms deployment
```

---

## Verification

After implementation:
1. Push backend change to main → verify tests run
2. Push frontend change to main → verify Vercel staging deploys
3. Create `api-v0.1.0` tag → verify Cloud Run deploys
4. Create `web-v0.1.0` tag → verify Vercel production deploys
5. Test CORS: staging frontend calling production API
