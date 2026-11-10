"""Celery tasks: give Strichliste products without an inventory item one."""

from __future__ import annotations

from hubra.core.modules import per_tenant_job
from hubra.core.tasks import celery_app


@celery_app.task(name="hubra_kasse.tasks.link_items")
@per_tenant_job("kasse")
def link_items() -> dict:
    from hubra.core.extensions import db

    from .items import link_missing

    linked = link_missing()
    db.session.commit()
    return {"linked": linked}
