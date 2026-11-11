"""Celery tasks: give Strichliste products without an inventory item one;
clear links to rows that are gone (hubra_kasse.links)."""

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


@celery_app.task(name="hubra_kasse.tasks.purge_orphans")
@per_tenant_job("kasse")
def purge_orphans() -> dict:
    from hubra.core.extensions import db

    from .links import purge_orphans as purge

    done = purge()
    db.session.commit()
    return done
