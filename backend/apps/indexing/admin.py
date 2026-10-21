from apps.accounts.admin_site import register

from .models import IndexBuildJob, IndexGeneration, IndexMembership, IndexValidation

# Mirrors what is in Qdrant and OpenSearch; publish and roll back through the console.
register(
    IndexGeneration, IndexBuildJob, IndexMembership, IndexValidation,
    save_warning="Saved in PostgreSQL only: Qdrant and OpenSearch were not changed. Publish and roll back from the console.",
)  # fmt: skip
