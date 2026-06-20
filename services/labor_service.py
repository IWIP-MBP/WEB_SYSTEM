from sqlalchemy import select, func
from models import labor_inventory

def get_item_stock(db, item_id):
    in_qty = db.execute(select(func.sum(labor_inventory.c.quantity)).where(
        labor_inventory.c.item_id == item_id,
        labor_inventory.c.change_type == "in"
    )).scalar() or 0
    out_qty = db.execute(select(func.sum(labor_inventory.c.quantity)).where(
        labor_inventory.c.item_id == item_id,
        labor_inventory.c.change_type == "out"
    )).scalar() or 0
    return in_qty - out_qty
