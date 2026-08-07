from __future__ import annotations

import pytest
from engine.categories import (
    _confidence_label,
    _is_persistence_layer_file,
    classify_files,
)
from engine.agent_routing import files_for_domain
from engine.models import ChangedFile


def test_domain_model_not_database():
    """Verify that backend/engine/models.py (a Pydantic model file) is categorized
    under 'Application/Core Logic' and NOT 'Data Layer'."""
    files = [
        ChangedFile(
            filename="backend/engine/models.py",
            status="modified",
            additions=64,
            deletions=5,
            changes=69,
        )
    ]
    buckets = classify_files(files)
    assert "backend/engine/models.py" in [f.filename for f in buckets["Application/Core Logic"]]
    assert "backend/engine/models.py" not in [f.filename for f in buckets["Data Layer"]]


def test_pydantic_models_not_database():
    """Verify that app/models.py is categorized under Application/Core Logic and not Data Layer."""
    files = [
        ChangedFile(
            filename="app/models.py",
            status="modified",
            additions=10,
            deletions=2,
            changes=12,
        )
    ]
    buckets = classify_files(files)
    assert "app/models.py" in [f.filename for f in buckets["Application/Core Logic"]]
    assert "app/models.py" not in [f.filename for f in buckets["Data Layer"]]


def test_alembic_migration_is_database():
    """Verify that actual migration files are categorized under Data Layer."""
    files = [
        ChangedFile(
            filename="alembic/versions/0001_add_users.py",
            status="added",
            additions=45,
            deletions=0,
            changes=45,
        )
    ]
    buckets = classify_files(files)
    assert "alembic/versions/0001_add_users.py" in [f.filename for f in buckets["Data Layer"]]


def test_sql_file_is_database():
    """Verify that raw SQL files are categorized under Data Layer."""
    files = [
        ChangedFile(
            filename="db/schema.sql",
            status="modified",
            additions=20,
            deletions=5,
            changes=25,
        )
    ]
    buckets = classify_files(files)
    assert "db/schema.sql" in [f.filename for f in buckets["Data Layer"]]


def test_prisma_schema_is_database():
    """Verify that Prisma schemas are categorized under Data Layer."""
    files = [
        ChangedFile(
            filename="prisma/schema.prisma",
            status="modified",
            additions=15,
            deletions=2,
            changes=17,
        )
    ]
    buckets = classify_files(files)
    assert "prisma/schema.prisma" in [f.filename for f in buckets["Data Layer"]]


def test_workflow_is_cicd():
    """Verify that GitHub Actions workflows are categorized under CI/CD."""
    files = [
        ChangedFile(
            filename=".github/workflows/pr-sentinel.yml",
            status="modified",
            additions=5,
            deletions=5,
            changes=10,
        )
    ]
    buckets = classify_files(files)
    assert ".github/workflows/pr-sentinel.yml" in [f.filename for f in buckets["CI/CD"]]


def test_auth_file_is_authentication():
    """Verify that auth files are categorized under Authentication."""
    files = [
        ChangedFile(
            filename="backend/auth/tokens.py",
            status="modified",
            additions=30,
            deletions=10,
            changes=40,
        )
    ]
    buckets = classify_files(files)
    assert "backend/auth/tokens.py" in [f.filename for f in buckets["Authentication"]]


def test_readme_is_documentation():
    """Verify that README files are categorized under Documentation."""
    files = [
        ChangedFile(
            filename="README.md",
            status="modified",
            additions=12,
            deletions=4,
            changes=16,
        )
    ]
    buckets = classify_files(files)
    assert "README.md" in [f.filename for f in buckets["Documentation"]]


def test_confidence_label_bands():
    """Verify confidence integer scores translate correctly to High/Medium/Low tiers."""
    assert _confidence_label(85) == "High"
    assert _confidence_label(75) == "High"
    assert _confidence_label(60) == "Medium"
    assert _confidence_label(50) == "Medium"
    assert _confidence_label(40) == "Low"
    assert _confidence_label(10) == "Low"


def test_agent_routing_no_false_positive():
    """Verify that agent_routing does not send backend/engine/models.py to the database specialist agent."""
    files = [
        ChangedFile(
            filename="backend/engine/models.py",
            status="modified",
            additions=60,
            deletions=5,
            changes=65,
        )
    ]
    db_files = files_for_domain(files, "database")
    assert len(db_files) == 0

    migration_files = [
        ChangedFile(
            filename="migrations/versions/001_init.py",
            status="added",
            additions=50,
            deletions=0,
            changes=50,
        )
    ]
    db_files_real = files_for_domain(migration_files, "database")
    assert len(db_files_real) == 1
