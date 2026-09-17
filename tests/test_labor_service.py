from sqlalchemy import insert

import services.labor_service as labor
from models import labor_inventory


def _movement(db, item_id, change_type, quantity):
    db.execute(insert(labor_inventory).values(item_id=item_id, change_type=change_type, quantity=quantity))


class TestGetItemStock:
    def test_no_movements_is_zero(self, db):
        assert labor.get_item_stock(db, 1) == 0

    def test_in_minus_out(self, db):
        _movement(db, 1, "in", 100)
        _movement(db, 1, "in", 50)
        _movement(db, 1, "out", 30)
        db.commit()
        assert labor.get_item_stock(db, 1) == 120

    def test_only_in(self, db):
        _movement(db, 5, "in", 10)
        db.commit()
        assert labor.get_item_stock(db, 5) == 10

    def test_isolated_per_item(self, db):
        _movement(db, 1, "in", 100)
        _movement(db, 2, "in", 7)
        _movement(db, 2, "out", 2)
        db.commit()
        assert labor.get_item_stock(db, 1) == 100
        assert labor.get_item_stock(db, 2) == 5

    def test_can_go_negative(self, db):
        _movement(db, 3, "out", 5)
        db.commit()
        assert labor.get_item_stock(db, 3) == -5
