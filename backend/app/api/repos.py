"""Repository API routes — placeholder for Step 3 (GitHub integration).

Step 2 only needs project-level CRUD. This module exists to keep the
router structure clean for when Step 3 adds GitHub OAuth, cloning, and
real repository ingestion endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/repos", tags=["repositories"])


@router.get("")
def list_repos():
    """Placeholder — Step 3 will implement GitHub repo listing."""
    return {"message": "Not implemented yet — see Step 3 (GitHub integration)"}
