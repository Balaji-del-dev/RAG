"""The six roles and the 19 permissions (docs/plan/01-backend.md §2.2).

Data migrations call sync_roles(apps) with historical models, so every
environment gets exactly this set. Change it here, then add a migration
that calls sync_roles again.
"""

PERMISSIONS: dict[str, str] = {
    "rag.ask": "Ask questions",
    "documents.view": "See and open documents in your access groups",
    "feedback.create": "Rate answers",
    "documents.upload": "Upload documents",
    "documents.manage": "Upload new versions of documents and delete them",
    "documents.manage_access": "Choose which access groups may read a document",
    "jobs.view": "See processing jobs",
    "jobs.retry": "Retry or cancel processing jobs",
    "pipelines.view": "See pipelines, models and settings",
    "pipelines.edit": "Edit draft pipeline versions and settings",
    "indexes.view": "See index generations",
    "indexes.build": "Build and validate index generations",
    "evaluation.view": "See evaluation runs and results",
    "evaluation.manage_datasets": "Create and edit evaluation datasets",
    "evaluation.run": "Start evaluation runs",
    "failures.review": "Review failure cases",
    "releases.approve": "Approve and publish releases; roll back index generations",
    "accounts.manage": "Manage users, roles, access groups and sessions",
    "audit.read": "Read the audit log",
}

ROLES: dict[str, tuple[str, list[str]]] = {
    "User": (
        "Every account: ask questions, open cited documents, give feedback",
        ["rag.ask", "documents.view", "feedback.create"],
    ),
    "Knowledge manager": (
        "Upload, version and delete documents; choose who may read them",
        ["documents.upload", "documents.manage", "documents.manage_access", "jobs.view", "jobs.retry"],
    ),
    "Pipeline engineer": (
        "Edit draft pipelines and settings; build indexes",
        ["pipelines.view", "pipelines.edit", "indexes.view", "indexes.build", "jobs.view", "jobs.retry"],
    ),
    "Evaluator": (
        "Manage datasets, run evaluations, review failures",
        ["evaluation.view", "evaluation.manage_datasets", "evaluation.run", "failures.review", "pipelines.view"],
    ),
    "Release approver": (
        "Approve and publish evaluated releases (never their own change)",
        ["releases.approve", "evaluation.view", "pipelines.view", "indexes.view"],
    ),
    "Admin": (
        "Manage users, roles, access groups and sessions; read the audit log",
        ["accounts.manage", "audit.read"],
    ),
}

DEFAULT_ACCESS_GROUP = ("general", "Default group: every new user is added to it")


def sync_roles(apps, schema_editor=None) -> None:
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")
    AccessGroup = apps.get_model("accounts", "AccessGroup")

    perms = {}
    for codename, description in PERMISSIONS.items():
        perms[codename], _ = Permission.objects.update_or_create(codename=codename, defaults={"description": description})
    for name, (description, codenames) in ROLES.items():
        role, _ = Role.objects.update_or_create(name=name, defaults={"description": description, "is_system": True})
        RolePermission.objects.filter(role=role).exclude(permission__codename__in=codenames).delete()
        for codename in codenames:
            RolePermission.objects.get_or_create(role=role, permission=perms[codename])
    name, description = DEFAULT_ACCESS_GROUP
    AccessGroup.objects.get_or_create(name=name, defaults={"description": description})
