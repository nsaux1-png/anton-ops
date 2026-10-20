"""Tests for clusterlib.billing: money, prices, job costs, credit batches and expiry, storage, the Slurm
credit limit and the grace step."""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))

from clusterlib import billing as b   # noqa: E402

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 11, 1, tzinfo=UTC)
RATES = {
    "units_per_gpu": 10,
    "partitions": {"gpu": "rtx5070ti"},
    "prices": [
        {"from": datetime.date(2026, 10, 1), "gpu_hour": {"rtx5070ti": "0.50"}, "cpu_core_hour": "0.02",
         "storage_gb_month": "0.05"},
        {"from": datetime.date(2027, 1, 1), "gpu_hour": {"rtx5070ti": "0.60"}, "cpu_core_hour": "0.02",
         "storage_gb_month": "0.04"},
    ],
}


class Money(unittest.TestCase):
    def test_to_micro_is_exact(self):
        self.assertEqual(b.to_micro("12.50"), 12_500_000)
        self.assertEqual(b.to_micro(0.1), 100_000)
        self.assertEqual(b.to_micro("0.000001"), 1)
        self.assertEqual(b.to_micro(3), 3_000_000)
        with self.assertRaises(b.BillingError):
            b.to_micro("0.0000001")
        with self.assertRaises(b.BillingError):
            b.to_micro("lots")

    def test_show_rounds_half_up_to_cents(self):
        self.assertEqual(b.show(12_345_000), "12.35")
        self.assertEqual(b.show(12_344_999), "12.34")
        self.assertEqual(b.show(-5_000), "-0.01")
        self.assertEqual(b.show(0), "0.00")
        self.assertEqual(b.show(-4), "0.00")


class Prices(unittest.TestCase):
    def test_rates_file_checks(self):
        self.assertEqual(b.check_rates(RATES), [])
        broken = dict(RATES, prices=[dict(RATES["prices"][0], gpu_hour={})])
        self.assertTrue(any("no gpu_hour price for rtx5070ti" in p for p in b.check_rates(broken)))
        backwards = dict(RATES, prices=list(reversed(RATES["prices"])))
        self.assertTrue(any("dates must go up" in p for p in b.check_rates(backwards)))
        negative = dict(RATES, prices=[dict(RATES["prices"][0], cpu_core_hour="-1")])
        self.assertTrue(any("negative" in p for p in b.check_rates(negative)))

    def test_default_prices_change_on_their_date(self):
        self.assertEqual(b.default_prices_at(RATES, "2026-12-31")["gpu_hour"]["rtx5070ti"], 500_000)
        self.assertEqual(b.default_prices_at(RATES, "2027-01-01")["gpu_hour"]["rtx5070ti"], 600_000)
        with self.assertRaises(b.BillingError):
            b.default_prices_at(RATES, "2026-09-30")

    def test_customer_overrides_and_discount(self):
        d = b.default_prices_at(RATES, T0)
        self.assertEqual(b.customer_prices(d, {}), d)
        p = b.customer_prices(d, {"rates": {"gpu_hour.rtx5070ti": "0.40"}})
        self.assertEqual(p["gpu_hour"]["rtx5070ti"], 400_000)
        self.assertEqual(p["storage_gb_month"], 50_000)                 # not overridden: the default
        p = b.customer_prices(d, {"discount_percent": 20})
        self.assertEqual(p["gpu_hour"]["rtx5070ti"], 400_000)
        self.assertEqual(p["cpu_core_hour"], 16_000)
        p = b.customer_prices(d, {"discount_percent": 20, "rates": {"storage_gb_month": "0.10"}})
        self.assertEqual(p["storage_gb_month"], 100_000)                # their own price wins over the discount
        with self.assertRaises(b.BillingError):
            b.customer_prices(d, {"rates": {"gpu_hour.h100": "2"}})
        with self.assertRaises(b.BillingError):
            b.customer_prices(d, {"rates": {"shoes": "2"}})
        with self.assertRaises(b.BillingError):
            b.customer_prices(d, {"discount_percent": 120})

    def test_unit_prices(self):
        p = b.default_prices_at(RATES, T0)
        self.assertEqual(b.unit_hour_price(p, RATES, "gpu"), 50_000)    # 0.50 per GPU-hour / 10 units
        self.assertEqual(b.unit_hour_price(p, RATES, "cpu"), 10_000)    # 0.02 per core-hour / 2 threads
        self.assertEqual(b.highest_unit_hour_price(p, RATES, ["gpu", "cpu"]), 50_000)


class JobCosts(unittest.TestCase):
    def test_one_gpu_for_an_hour_costs_the_gpu_hour_price(self):
        self.assertEqual(b.job_cost(10, 3600, 50_000), 500_000)

    def test_charging_in_pieces_adds_up_to_charging_at_once(self):
        """Hourly charges are differences of the cost so far, so they never drift from the total."""
        units, price = 37, 49_999
        charged = 0
        for elapsed in (0, 61, 3600, 3601, 7207, 10_000, 86_399):
            due = b.job_cost(units, elapsed, price) - charged
            self.assertGreaterEqual(due, 0)
            charged += due
        self.assertEqual(charged, b.job_cost(units, 86_399, price))

    def test_never_overcharges(self):
        self.assertEqual(b.job_cost(1, 1, 1), 0)


def batch(i, amount, days_until_expiry, used=0):
    return b.Batch(id=i, amount=amount, expires_at=T0 + datetime.timedelta(days=days_until_expiry), used=used)


class Batches(unittest.TestCase):
    def test_soonest_expiring_is_used_first(self):
        bs = [batch(1, 100, 300), batch(2, 100, 30), batch(3, 100, 200)]
        taken, left = b.spend(bs, 150, T0)
        self.assertEqual(taken, [(2, 100), (3, 50)])
        self.assertEqual(left, 0)

    def test_a_charge_bigger_than_everything_leaves_debt(self):
        bs = [batch(1, 100, 30)]
        taken, left = b.spend(bs, 130, T0)
        self.assertEqual(taken, [(1, 100)])
        self.assertEqual(left, 30)

    def test_expired_batches_are_never_spent(self):
        bs = [batch(1, 100, -1), batch(2, 100, 10)]
        taken, _ = b.spend(bs, 50, T0)
        self.assertEqual(taken, [(2, 50)])

    def test_expiry_writes_off_only_what_is_left(self):
        bs = [batch(1, 100, -1, used=30), batch(2, 100, 10), batch(3, 50, -5, used=50)]
        self.assertEqual(b.expire(bs, T0), [(1, 70)])
        self.assertEqual(bs[0].remaining, 0)
        self.assertEqual(b.expire(bs, T0), [])                 # never twice

    def test_expiry_is_exactly_at_the_moment(self):
        at = batch(1, 100, 0)
        self.assertEqual(b.expire([at], T0), [(1, 100)])

    def test_available_credit(self):
        bs = [batch(1, 100, -1), batch(2, 100, 10, used=40)]
        self.assertEqual(b.available(bs, debt=0, now=T0), 60)
        self.assertEqual(b.available(bs, debt=80, now=T0), -20)

    def test_new_batches_last_twelve_months(self):
        self.assertEqual(b.new_batch_expiry(T0), T0 + datetime.timedelta(days=365))


class Storage(unittest.TestCase):
    def test_only_a_new_peak_costs(self):
        peak, extra = b.storage_increment(0, 10 * b.GIB)
        self.assertEqual((peak, extra), (10 * b.GIB, 10 * b.GIB))
        peak, extra = b.storage_increment(peak, 4 * b.GIB)
        self.assertEqual((peak, extra), (10 * b.GIB, 0))
        peak, extra = b.storage_increment(peak, 12 * b.GIB)
        self.assertEqual((peak, extra), (12 * b.GIB, 2 * b.GIB))

    def test_month_charge_equals_peak_times_price(self):
        price = 50_000
        peak, charged = 0, 0
        for reading in (1, 5, 3, 7, 7, 2, 6):
            peak, extra = b.storage_increment(peak, reading * b.GIB)
            charged += b.storage_cost(extra, price)
        self.assertEqual(charged, b.storage_cost(7 * b.GIB, price))
        self.assertEqual(charged, 7 * price)


class SlurmLimit(unittest.TestCase):
    def test_limit_is_usage_plus_what_credit_buys(self):
        # 5.00 credits at 50,000 micro per unit-hour = 100 unit-hours = 6000 unit-minutes
        self.assertEqual(b.qos_limit(1234, 5_000_000, 50_000), 1234 + 6000)

    def test_second_top_up_raises_the_limit_even_after_lifetime_usage_exceeds_the_balance(self):
        """The bug the review found: a limit equal to the balance blocks a customer whose lifetime
        usage is already above it."""
        lifetime_used = 50_000
        self.assertGreater(b.qos_limit(lifetime_used, 1_000_000, 50_000), lifetime_used)

    def test_no_credit_means_no_more_than_used(self):
        self.assertEqual(b.qos_limit(500, 0, 50_000), 500)
        self.assertEqual(b.qos_limit(500, -3_000_000, 50_000), 500)

    def test_zero_price_is_refused(self):
        with self.assertRaises(b.BillingError):
            b.qos_limit(0, 1, 0)


class Grace(unittest.TestCase):
    def test_nothing_happens_while_there_is_credit(self):
        self.assertEqual(b.grace_updates(1, [b.RunningJob("7", 600, 60)]), [])

    def test_out_of_credit_gives_ten_more_minutes_once(self):
        jobs = [b.RunningJob("7", 3601, 600), b.RunningJob("8", 60, 600, graced=True)]
        self.assertEqual(b.grace_updates(0, jobs), [("7", 61 + b.GRACE_MINUTES)])

    def test_never_lengthens_a_job(self):
        self.assertEqual(b.grace_updates(-5, [b.RunningJob("7", 60, 5)]), [])


class Statements(unittest.TestCase):
    def test_closing_balance(self):
        s = b.Statement(opening=1_000, topups=500, charges=300, storage=50, expiries=100, refunds=20, adjustments=-10)
        self.assertEqual(s.closing, 1_060)



class CrossCheck(unittest.TestCase):
    def test_agreement_is_empty(self):
        self.assertEqual(b.compare_charges({1: 500, 2: 7}, {1: 500, 2: 7}), [])

    def test_every_kind_of_difference_is_reported(self):
        out = b.compare_charges({1: 500_000, 2: 700_000}, {1: 400_000, 3: 100_000})
        self.assertEqual(len(out), 3)
        self.assertIn("job record 1: charged 0.40, Slurm says 0.50", out[0])
        self.assertIn("job record 2: Slurm says it cost 0.70 but it was never charged", out[1])
        self.assertIn("job record 3: charged 0.10 but Slurm has no such finished job", out[2])


if __name__ == "__main__":
    unittest.main()
