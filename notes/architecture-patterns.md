# Refactoring Idea: Service + Repository (Layered Architecture)

This is a simple design pattern that helps you keep backend code clean, testable, and easy to change.

## Why refactor?
When everything lives in `main.py`, it gets hard to:
- Find logic quickly.
- Test logic without running the server.
- Swap storage systems (local files -> Firestore).

So we split responsibilities.

## The Pattern (Plain English)
- **Routes (Controller layer)**: Only handles HTTP details (inputs/outputs).
- **Service layer**: The "brain" that does the real work (parse files, build summaries).
- **Repository layer**: The "storage helper" that reads/writes data (local JSON now, Firestore later).

Each layer has one job. That makes the code easier to read and less fragile.

## Proposed Structure
```
backend/
  app/
    main.py              # Create FastAPI app, include routes
    api/
      routes.py          # Request/response handling only
    services/
      transaction_service.py  # Parsing + analysis logic
    repositories/
      local_repo.py      # Local JSON storage (current)
      firestore_repo.py  # Firestore storage (later)
    schemas/
      models.py          # Pydantic request/response models
```

## How It Flows
1. A request hits `/upload`.
2. **Route** passes files to the **Service**.
3. **Service** parses files and builds summaries.
4. **Repository** saves everything.
5. **Route** returns a response.

## Benefits
- **Cleaner files**: `main.py` stays small.
- **Easier tests**: Test the service without running a server.
- **Easy migration**: Swap `local_repo` with `firestore_repo` later.
- **Team-friendly**: Different people can work on different layers safely.

## Key Idea to Remember
> "Controllers talk to services, services talk to repositories."

If you keep this rule, your code stays organized as the project grows.
