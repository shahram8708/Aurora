from app.extensions import celery
from .inventory_service import expire_reservations


@celery.task(name="app.commerce.expire_inventory_reservations")
def expire_inventory_reservations_task():
    expire_reservations()
