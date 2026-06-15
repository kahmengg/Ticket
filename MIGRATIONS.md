# Database Migrations With Alembic

Alembic is the migration tool for SQLAlchemy.

In plain English: it keeps track of database structure changes over time.

Without Alembic, changing production tables is manual and risky. With Alembic, schema changes become versioned files in `alembic/versions/`.

Example:

```text
You add a new model field in app/models.py
Alembic creates a migration file
Render/Supabase can apply that migration safely
The database records which migration version it is on
```

## Current Setup

The first migration is:

```text
alembic/versions/20260615_0001_initial_schema.py
```

It represents the current app schema:

- artists
- venues
- sources
- events
- alerts
- telegram_subscribers
- watchlist_keywords

The app still calls `Base.metadata.create_all()` on startup. That keeps fresh deploys simple. After tables exist, startup creates/stamps the `alembic_version` table with the initial revision if needed.

That means your current production database can keep running, and future schema changes can use Alembic migrations.

## Common Commands

Run all pending migrations:

```powershell
.venv\Scripts\alembic.exe upgrade head
```

Show current database migration version:

```powershell
.venv\Scripts\alembic.exe current
```

Create a new auto-generated migration after changing `app/models.py`:

```powershell
.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
```

Then review the generated file under:

```text
alembic/versions/
```

Apply it:

```powershell
.venv\Scripts\alembic.exe upgrade head
```

## Production Workflow

For future schema changes:

1. Change `app/models.py`.
2. Generate a migration:

```powershell
.venv\Scripts\alembic.exe revision --autogenerate -m "add something"
```

3. Review the migration file. Do not blindly trust autogenerate.
4. Run tests locally.
5. Commit and push.
6. Run migration against production.

For Render, the simplest next step is to run migrations manually from your local machine by temporarily setting `DATABASE_URL` to your Supabase connection string, then running:

```powershell
.venv\Scripts\alembic.exe upgrade head
```

Later, you can add migrations to the Render build/release process, but manual is safer while this project is small.

## Important

Do not use Alembic downgrade on production unless you are very sure. Downgrades can delete tables or columns.
