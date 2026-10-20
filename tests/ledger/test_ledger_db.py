"""The ledger against a real database: the scratch copy cluster_ledger_test, emptied before each test.

Needs root (the database password is root-only), so tests/live/test_ledger.py runs this with sudo.
"""

import datetime
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from clusterlib import billing as b            # noqa: E402
from clusterlib.ledger import Ledger            # noqa: E402

C = "c0001"
T0 = datetime.datetime(2026, 11, 3, 12, 0, 0)
HOUR = datetime.timedelta(hours=1)
M = b.MICRO


def fresh():
    ledger = Ledger(database="cluster_ledger_test")
    with ledger.db.cursor() as c:
        c.execute("SET FOREIGN_KEY_CHECKS=0")
        c.execute("SHOW TABLES")
        for (table,) in c.fetchall():
            c.execute(f"DROP TABLE {table}")
        c.execute("SET FOREIGN_KEY_CHECKS=1")
    ledger.db.commit()
    ledger.setup()
    return ledger


class Credits(unittest.TestCase):
    def setUp(self):
        self.l = fresh()
        self.addCleanup(self.l.close)

    def test_top_up_then_spend_soonest_expiring_first(self):
        late = self.l.add_credit(C, "topup", 100 * M, "INV-1", "", "t", at=T0)
        soon = self.l.add_credit(C, "grant", 50 * M, "G-1", "", "t", at=T0, expires_at=T0 + 30 * 24 * HOUR)
        self.l.debit(C, "charge", 70 * M, "job:1:3600", "", "t", at=T0 + HOUR)
        batches = {x.id: x for x in self.l.balance(C, T0 + HOUR)["batches"]}
        self.assertEqual(batches[soon].remaining, 0)
        self.assertEqual(batches[late].remaining, 80 * M)
        bal = self.l.balance(C, T0 + HOUR)
        self.assertEqual((bal["balance"], bal["available"], bal["debt"]), (80 * M, 80 * M, 0))

    def test_the_same_reference_never_counts_twice(self):
        self.assertIsNotNone(self.l.add_credit(C, "topup", 10 * M, "INV-9", "", "t", at=T0))
        self.assertIsNone(self.l.add_credit(C, "topup", 10 * M, "INV-9", "", "t", at=T0))
        self.assertIsNotNone(self.l.debit(C, "charge", 1 * M, "job:5:60", "", "t", at=T0))
        self.assertIsNone(self.l.debit(C, "charge", 1 * M, "job:5:60", "", "t", at=T0))
        self.assertEqual(self.l.balance(C, T0)["balance"], 9 * M)

    def test_debt_is_paid_first_by_the_next_top_up(self):
        self.l.add_credit(C, "topup", 10 * M, "INV-1", "", "t", at=T0)
        self.l.debit(C, "charge", 15 * M, "job:1:1", "", "t", at=T0 + HOUR)
        bal = self.l.balance(C, T0 + HOUR)
        self.assertEqual((bal["available"], bal["debt"]), (-5 * M, 5 * M))
        self.l.add_credit(C, "topup", 20 * M, "INV-2", "", "t", at=T0 + 2 * HOUR)
        bal = self.l.balance(C, T0 + 2 * HOUR)
        self.assertEqual((bal["balance"], bal["available"], bal["debt"]), (15 * M, 15 * M, 0))

    def test_expiry(self):
        old = self.l.add_credit(C, "topup", 10 * M, "INV-1", "", "t", at=T0 - 400 * 24 * HOUR)
        self.l.add_credit(C, "topup", 5 * M, "INV-2", "", "t", at=T0)
        self.l.debit(C, "charge", 4 * M, "job:1:1", "", "t", at=T0 - 300 * 24 * HOUR)
        self.assertEqual(self.l.expire(C, "t", T0), [(old, 6 * M)])
        self.assertEqual(self.l.expire(C, "t", T0), [])                          # never twice
        bal = self.l.balance(C, T0)
        self.assertEqual((bal["balance"], bal["available"]), (5 * M, 5 * M))
        self.l.debit(C, "charge", 1 * M, "job:2:1", "", "t", at=T0)               # comes from the live batch
        self.assertEqual(self.l.balance(C, T0)["available"], 4 * M)

    def test_negative_adjustment(self):
        self.l.add_credit(C, "topup", 10 * M, "INV-1", "", "t", at=T0)
        self.l.debit(C, "adjustment", 2 * M, "ADJ-1", "correction", "t", at=T0)
        self.assertEqual(self.l.balance(C, T0)["balance"], 8 * M)

    def test_statements_chain_month_to_month(self):
        self.l.add_credit(C, "topup", 100 * M, "INV-1", "", "t", at=datetime.datetime(2026, 10, 5))
        self.l.debit(C, "charge", 30 * M, "job:1:1", "", "t", at=datetime.datetime(2026, 10, 20))
        self.l.debit(C, "storage", 5 * M, "storage:2026-11:1", "", "t", at=datetime.datetime(2026, 11, 1, 1))
        self.l.add_credit(C, "grant", 10 * M, "G-1", "", "t", at=datetime.datetime(2026, 11, 2))
        oct_, nov = self.l.statement(C, "2026-10"), self.l.statement(C, "2026-11")
        self.assertEqual((oct_.opening, oct_.topups, oct_.charges, oct_.closing), (0, 100 * M, 30 * M, 70 * M))
        self.assertEqual(nov.opening, oct_.closing)
        self.assertEqual((nov.storage, nov.grants, nov.closing), (5 * M, 10 * M, 75 * M))
        self.assertEqual(nov.closing, self.l.balance(C, T0)["balance"])

    def test_two_writers_never_overspend_a_batch(self):
        batch = self.l.add_credit(C, "topup", 100 * M, "INV-1", "", "t", at=T0)
        errors = []

        def spend(n):
            other = Ledger(database="cluster_ledger_test")
            try:
                for i in range(10):
                    other.debit(C, "charge", 6 * M, f"job:{n}:{i}", "", "t", at=T0)
            except Exception as e:      # noqa: BLE001
                errors.append(e)
            finally:
                other.close()

        threads = [threading.Thread(target=spend, args=(n,)) for n in (1, 2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        with self.l.db.cursor() as c:
            c.execute("SELECT SUM(amount) FROM allocations WHERE batch_id=%s", (batch,))
            self.assertEqual(int(c.fetchone()[0]), 100 * M)          # exactly the batch, never more
        self.l.db.rollback()
        bal = self.l.balance(C, T0)
        self.assertEqual((bal["balance"], bal["debt"]), (-20 * M, 20 * M))


class Jobs(unittest.TestCase):
    def setUp(self):
        self.l = fresh()
        self.addCleanup(self.l.close)
        self.l.add_credit(C, "topup", 100 * M, "INV-1", "", "t", at=T0 - HOUR)
        self.l.record_job(501, "77", C, "zz01", "gpu", 10, 50_000, T0)

    def test_hourly_charges_add_up_to_the_whole_job(self):
        charged = 0
        for elapsed in (3600, 7200, 7300):
            charged += self.l.charge_job(501, elapsed, "RUNNING", None, "t", at=T0 + datetime.timedelta(seconds=elapsed))
        charged += self.l.charge_job(501, 9000, "COMPLETED", T0 + datetime.timedelta(seconds=9000), "t")
        self.assertEqual(charged, b.job_cost(10, 9000, 50_000))
        self.assertEqual(self.l.job(501)["charged"], charged)
        self.assertEqual(self.l.balance(C, T0 + 3 * HOUR)["balance"], 100 * M - charged)

    def test_running_the_charge_again_charges_nothing(self):
        self.l.charge_job(501, 3600, "RUNNING", None, "t", at=T0 + HOUR)
        self.assertEqual(self.l.charge_job(501, 3600, "RUNNING", None, "t", at=T0 + HOUR), 0)
        self.assertEqual(self.l.charge_job(501, 3000, "RUNNING", None, "t", at=T0 + HOUR), 0)   # never backwards

    def test_finished_jobs_are_never_charged_again(self):
        self.l.charge_job(501, 600, "COMPLETED", T0 + HOUR, "t")
        self.assertEqual(self.l.charge_job(501, 99_999, "COMPLETED", T0 + HOUR, "t"), 0)

    def test_refund(self):
        self.l.charge_job(501, 3600, "NODE_FAIL", T0 + HOUR, "t")
        self.assertEqual(self.l.refund_job(501, "node failed", "t", at=T0 + HOUR), 500_000)
        self.assertEqual(self.l.refund_job(501, "node failed", "t", at=T0 + HOUR), 0)
        self.assertEqual(self.l.balance(C, T0 + HOUR)["balance"], 100 * M)

    def test_jobs_for_a_month(self):
        self.l.record_job(502, "78", C, "zz02", "gpu", 10, 50_000, T0)
        self.assertEqual({r["job_id"] for r in self.l.jobs_for(C, None, "2026-11")}, {"77", "78"})
        self.assertEqual({r["job_id"] for r in self.l.jobs_for(C, "zz02", "2026-11")}, {"78"})
        self.assertEqual(self.l.jobs_for(C, None, "2026-10"), [])


class Storage(unittest.TestCase):
    def setUp(self):
        self.l = fresh()
        self.addCleanup(self.l.close)

    def test_month_charge_is_the_peak_times_the_price(self):
        price = 50_000
        at = datetime.datetime(2026, 11, 1, 0, 30)
        total = 0
        for i, gib in enumerate((2, 5, 3, 5, 7, 1)):
            total += self.l.record_storage(C, gib * b.GIB, price, "t", at + i * HOUR)
        self.assertEqual(total, 7 * price)
        self.assertEqual(self.l.storage_month(C, "2026-11")["peak_bytes"], 7 * b.GIB)

    def test_a_new_month_starts_from_zero_at_its_own_price(self):
        self.l.record_storage(C, 4 * b.GIB, 50_000, "t", datetime.datetime(2026, 11, 30, 23))
        cost = self.l.record_storage(C, 4 * b.GIB, 60_000, "t", datetime.datetime(2026, 12, 1, 0, 5))
        self.assertEqual(cost, 4 * 60_000)
        later = self.l.record_storage(C, 5 * b.GIB, 99_000, "t", datetime.datetime(2026, 12, 2))
        self.assertEqual(later, 60_000)                       # still December's price


class Prices(unittest.TestCase):
    def setUp(self):
        self.l = fresh()
        self.addCleanup(self.l.close)

    def test_history_only_grows_when_prices_change(self):
        p1 = {"gpu_hour": {"rtx5070ti": 500_000}, "cpu_core_hour": 20_000, "storage_gb_month": 50_000}
        p2 = dict(p1, storage_gb_month=40_000)
        self.assertTrue(self.l.record_prices(C, p1, T0))
        self.assertFalse(self.l.record_prices(C, p1, T0 + HOUR))
        self.assertTrue(self.l.record_prices(C, p2, T0 + 2 * HOUR))
        self.assertEqual(self.l.prices_at(C, T0 + HOUR), p1)
        self.assertEqual(self.l.prices_at(C, T0 + 3 * HOUR), p2)
        self.assertIsNone(self.l.prices_at(C, T0 - HOUR))
        self.assertEqual(len(self.l.price_history(C)), 2)


if __name__ == "__main__":
    unittest.main()
