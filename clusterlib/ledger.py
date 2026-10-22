"""The ledger: every credit movement, in the cluster_ledger database on anton (SOP-161).

Append-only: nothing is edited or deleted; corrections are new entries. Every entry belongs to one
customer and has a reference that's unique for that customer (an invoice number, a job charge key),
so doing the same thing twice never counts twice.

  entries       top-ups, grants, refunds, adjustments (+) and charges, storage, expiries (-)
  batches       each top-up, grant or refund is a batch of credit with an expiry date
  allocations   which batch paid for which charge; batch NULL = not yet paid (debt)
  job_charges   what each Slurm job record (sacct DBIndex) has been charged so far
  storage_*     hourly readings and each month's peak
  price_history each customer's prices, and from when

The money logic is in clusterlib.billing; this module only stores and reads it.
"""

import datetime
import json

import pymysql

from clusterlib import billing

SCHEMA_VERSION = 2
# Slurm 26.05's job record IDs (sacct DBIndex) go above 2^63, so the column is unsigned (2026-10-21).
CLAMPED_DB_INDEX = 2**63 - 1      # what MariaDB stored instead, in a signed column, under INSERT IGNORE
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS schema_version (version INT NOT NULL) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS entries (
         id BIGINT AUTO_INCREMENT PRIMARY KEY,
         customer VARCHAR(16) NOT NULL,
         kind ENUM('topup','grant','refund','adjustment','charge','storage','expiry') NOT NULL,
         amount BIGINT NOT NULL,
         ref VARCHAR(160) NOT NULL,
         note VARCHAR(255) NOT NULL DEFAULT '',
         operator VARCHAR(64) NOT NULL,
         created_at DATETIME(6) NOT NULL,
         UNIQUE KEY customer_ref (customer, ref),
         KEY customer_time (customer, created_at)
       ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS batches (
         id BIGINT PRIMARY KEY,
         customer VARCHAR(16) NOT NULL,
         amount BIGINT NOT NULL,
         expires_at DATETIME(6) NOT NULL,
         KEY customer_expiry (customer, expires_at),
         FOREIGN KEY (id) REFERENCES entries (id)
       ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS allocations (
         id BIGINT AUTO_INCREMENT PRIMARY KEY,
         entry_id BIGINT NOT NULL,
         batch_id BIGINT NULL,
         amount BIGINT NOT NULL,
         KEY by_entry (entry_id),
         KEY by_batch (batch_id),
         FOREIGN KEY (entry_id) REFERENCES entries (id)
       ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS job_charges (
         db_index BIGINT UNSIGNED PRIMARY KEY,
         job_id VARCHAR(32) NOT NULL,
         customer VARCHAR(16) NOT NULL,
         username VARCHAR(16) NOT NULL,
         partition_name VARCHAR(64) NOT NULL,
         units INT NOT NULL,
         unit_hour_price BIGINT NOT NULL,
         started_at DATETIME(6) NOT NULL,
         ended_at DATETIME(6) NULL,
         state VARCHAR(32) NOT NULL,
         charged_seconds BIGINT NOT NULL DEFAULT 0,
         charged BIGINT NOT NULL DEFAULT 0,
         refunded TINYINT NOT NULL DEFAULT 0,
         final TINYINT NOT NULL DEFAULT 0,
         graced TINYINT NOT NULL DEFAULT 0,
         KEY customer_start (customer, started_at)
       ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS storage_readings (
         customer VARCHAR(16) NOT NULL,
         at DATETIME(6) NOT NULL,
         used_bytes BIGINT NOT NULL,
         PRIMARY KEY (customer, at)
       ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS storage_months (
         customer VARCHAR(16) NOT NULL,
         month CHAR(7) NOT NULL,
         peak_bytes BIGINT NOT NULL,
         gb_month_price BIGINT NOT NULL,
         PRIMARY KEY (customer, month)
       ) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS price_history (
         id BIGINT AUTO_INCREMENT PRIMARY KEY,
         customer VARCHAR(16) NOT NULL,
         effective_from DATETIME(6) NOT NULL,
         prices TEXT NOT NULL,
         KEY customer_from (customer, effective_from)
       ) ENGINE=InnoDB""",
]

CREDIT_KINDS = ("topup", "grant", "refund", "adjustment")
DEBIT_KINDS = ("charge", "storage", "expiry", "adjustment")


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class Ledger:
    def __init__(self, database="cluster_ledger", user="cluster_billing",
                 password_file="/etc/cluster/secrets/billingdb-password",
                 socket="/var/lib/mysql/mysql.sock"):
        with open(password_file) as f:
            password = f.read().strip()
        # Strict: a value that doesn't fit is an error, never quietly changed.
        self.db = pymysql.connect(unix_socket=socket, user=user, password=password, database=database,
                                  autocommit=False, charset="utf8mb4",
                                  init_command="SET SESSION sql_mode='STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION'")

    def close(self):
        self.db.close()

    # --- setup --------------------------------------------------------------------------------------

    def setup(self):
        """Create the tables if they don't exist, and bring older ones up to SCHEMA_VERSION.
        Returns what it did, as text ("" if nothing)."""
        done = []
        with self.db.cursor() as c:
            c.execute("SHOW TABLES")
            before = {row[0] for row in c.fetchall()}
            for statement in SCHEMA:
                c.execute(statement)
            c.execute("SHOW TABLES")
            if {row[0] for row in c.fetchall()} != before:
                done.append("created tables")
            c.execute("SELECT version FROM schema_version")
            row = c.fetchone()
            if row is None:
                c.execute("INSERT INTO schema_version VALUES (%s)", (SCHEMA_VERSION,))
            elif row[0] < 2:
                done.append(self._migrate_to_2(c))
                c.execute("UPDATE schema_version SET version=2")
        self.db.commit()
        return "; ".join(done)

    def _migrate_to_2(self, c):
        """job_charges.db_index unsigned, and drop rows the signed column clamped (they never held money)."""
        c.execute("SELECT COUNT(*) FROM job_charges WHERE db_index=%s AND (charged<>0 OR refunded<>0)",
                  (CLAMPED_DB_INDEX,))
        if c.fetchone()[0]:
            raise billing.BillingError("a clamped job record holds charges: needs a person (ops log 2026-10-21)")
        c.execute("ALTER TABLE job_charges MODIFY db_index BIGINT UNSIGNED NOT NULL")
        dropped = c.execute("DELETE FROM job_charges WHERE db_index=%s", (CLAMPED_DB_INDEX,))
        return f"job record IDs now unsigned; dropped {dropped} clamped record(s) with no charges"

    # --- writing ------------------------------------------------------------------------------------

    def _lock(self, c, customer):
        """One writer per customer at a time (the hourly run and an admin's top-up can overlap)."""
        c.execute("SELECT GET_LOCK(%s, 30)", (f"ledger-{customer}",))
        if c.fetchone()[0] != 1:
            raise billing.BillingError(f"couldn't lock the ledger for {customer}")

    def _unlock(self, c, customer):
        c.execute("SELECT RELEASE_LOCK(%s)", (f"ledger-{customer}",))

    def _exists(self, c, customer, ref):
        c.execute("SELECT id FROM entries WHERE customer=%s AND ref=%s", (customer, ref))
        row = c.fetchone()
        return row[0] if row else None

    def _insert(self, c, customer, kind, amount, ref, note, operator, at):
        c.execute("INSERT INTO entries (customer, kind, amount, ref, note, operator, created_at) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s)", (customer, kind, amount, ref, note[:255], operator, at))
        return c.lastrowid

    def _batches(self, c, customer):
        c.execute("SELECT b.id, b.amount, b.expires_at, "
                  "COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN entries e ON e.id=a.entry_id "
                  "          WHERE a.batch_id=b.id AND e.kind<>'expiry'),0), "
                  "COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN entries e ON e.id=a.entry_id "
                  "          WHERE a.batch_id=b.id AND e.kind='expiry'),0) "
                  "FROM batches b WHERE b.customer=%s FOR UPDATE", (customer,))
        return [billing.Batch(id=r[0], amount=r[1], expires_at=r[2], used=int(r[3]), expired=int(r[4]))
                for r in c.fetchall()]

    def _debt(self, c, customer):
        c.execute("SELECT COALESCE(SUM(a.amount),0) FROM allocations a JOIN entries e ON e.id=a.entry_id "
                  "WHERE e.customer=%s AND a.batch_id IS NULL", (customer,))
        return int(c.fetchone()[0])

    def add_credit(self, customer, kind, amount, ref, note, operator, at=None, expires_at=None):
        """A top-up, grant, refund or positive adjustment: a new batch of credit, which first pays any
        unpaid charges. Returns the entry id, or None if this reference was already recorded."""
        if kind not in CREDIT_KINDS or amount <= 0:
            raise billing.BillingError("credit needs a positive amount and a credit kind")
        at = at or utcnow()

        def work(c):
            if self._exists(c, customer, ref):
                return None
            entry = self._insert(c, customer, kind, amount, ref, note, operator, at)
            c.execute("INSERT INTO batches VALUES (%s,%s,%s,%s)",
                      (entry, customer, amount, expires_at or billing.new_batch_expiry(at)))
            self._settle_debt(c, customer, entry, amount)
            return entry

        return self._in_transaction(customer, work)

    def _settle_debt(self, c, customer, batch_id, amount):
        """Move unpaid charges, oldest first, onto a new batch."""
        c.execute("SELECT a.entry_id, SUM(a.amount) FROM allocations a JOIN entries e ON e.id=a.entry_id "
                  "WHERE e.customer=%s AND a.batch_id IS NULL GROUP BY a.entry_id HAVING SUM(a.amount)>0 "
                  "ORDER BY a.entry_id", (customer,))
        left = amount
        for entry_id, owed in c.fetchall():
            if left <= 0:
                break
            part = min(int(owed), left)
            c.execute("INSERT INTO allocations (entry_id, batch_id, amount) VALUES (%s,%s,%s),(%s,NULL,%s)",
                      (entry_id, batch_id, part, entry_id, -part))
            left -= part

    def _debit_in(self, c, customer, kind, amount, ref, note, operator, at):
        """A debit inside a transaction that holds the customer's lock. None if already recorded."""
        if kind not in DEBIT_KINDS or amount < 0:
            raise billing.BillingError("debit needs a non-negative amount and a debit kind")
        if self._exists(c, customer, ref):
            return None
        entry = self._insert(c, customer, kind, -amount, ref, note, operator, at)
        taken, left = billing.spend(self._batches(c, customer), amount, at)
        for batch_id, part in taken:
            c.execute("INSERT INTO allocations (entry_id, batch_id, amount) VALUES (%s,%s,%s)", (entry, batch_id, part))
        if left:
            c.execute("INSERT INTO allocations (entry_id, batch_id, amount) VALUES (%s,NULL,%s)", (entry, left))
        return entry

    def _in_transaction(self, customer, work):
        """Run work(cursor) holding the customer's lock, as one transaction."""
        with self.db.cursor() as c:
            self._lock(c, customer)
            try:
                result = work(c)
                self.db.commit()
                return result
            except Exception:
                self.db.rollback()
                raise
            finally:
                self._unlock(c, customer)

    def debit(self, customer, kind, amount, ref, note, operator, at=None):
        """A charge, storage charge or expiry: taken from the batches that expire soonest; whatever no
        batch covers is debt. Returns the entry id, or None if this reference was already recorded."""
        at = at or utcnow()
        return self._in_transaction(customer, lambda c: self._debit_in(c, customer, kind, amount, ref, note,
                                                                       operator, at))

    def expire(self, customer, operator, now=None):
        """Write off what's left in this customer's expired batches. Returns [(batch id, amount)]."""
        now = now or utcnow()

        def work(c):
            done = []
            for batch_id, amount in billing.expire(self._batches(c, customer), now):
                entry = self._insert(c, customer, "expiry", -amount, f"expiry:{batch_id}",
                                     f"credit from entry {batch_id} expired", operator, now)
                c.execute("INSERT INTO allocations (entry_id, batch_id, amount) VALUES (%s,%s,%s)",
                          (entry, batch_id, amount))
                done.append((batch_id, amount))
            return done

        return self._in_transaction(customer, work)

    # --- reading ------------------------------------------------------------------------------------

    def balance(self, customer, now=None):
        """{"balance": sum of all entries, "available": what can still be spent, "debt", "batches"}."""
        now = now or utcnow()
        with self.db.cursor() as c:
            c.execute("SELECT COALESCE(SUM(amount),0) FROM entries WHERE customer=%s", (customer,))
            total = int(c.fetchone()[0])
            batches = self._batches(c, customer)
            debt = self._debt(c, customer)
        self.db.rollback()
        return {"balance": total, "available": billing.available(batches, debt, now), "debt": debt,
                "batches": sorted(batches, key=lambda b: (b.expires_at, b.id))}

    def entries(self, customer, start=None, end=None):
        sql = "SELECT id, kind, amount, ref, note, operator, created_at FROM entries WHERE customer=%s"
        args = [customer]
        if start:
            sql += " AND created_at >= %s"
            args.append(start)
        if end:
            sql += " AND created_at < %s"
            args.append(end)
        with self.db.cursor() as c:
            c.execute(sql + " ORDER BY created_at, id", args)
            rows = c.fetchall()
        self.db.rollback()
        return [dict(zip(("id", "kind", "amount", "ref", "note", "operator", "created_at"), r)) for r in rows]

    def statement(self, customer, month):
        """A month's statement ("2026-10"): opening balance, totals by kind, closing balance, entries."""
        start = datetime.datetime.strptime(month + "-01", "%Y-%m-%d")
        end = (start + datetime.timedelta(days=32)).replace(day=1)
        with self.db.cursor() as c:
            c.execute("SELECT COALESCE(SUM(amount),0) FROM entries WHERE customer=%s AND created_at < %s",
                      (customer, start))
            opening = int(c.fetchone()[0])
        s = billing.Statement(opening=opening)
        for e in self.entries(customer, start, end):
            s.lines.append(e)
            amount = e["amount"]
            if e["kind"] == "topup":
                s.topups += amount
            elif e["kind"] == "grant":
                s.grants += amount
            elif e["kind"] == "refund":
                s.refunds += amount
            elif e["kind"] == "adjustment":
                s.adjustments += amount
            elif e["kind"] == "charge":
                s.charges -= amount
            elif e["kind"] == "storage":
                s.storage -= amount
            elif e["kind"] == "expiry":
                s.expiries -= amount
        return s

    # --- jobs ---------------------------------------------------------------------------------------

    def job(self, db_index):
        with self.db.cursor(pymysql.cursors.DictCursor) as c:
            c.execute("SELECT * FROM job_charges WHERE db_index=%s", (db_index,))
            row = c.fetchone()
        self.db.rollback()
        return row

    def record_job(self, db_index, job_id, customer, username, partition, units, unit_hour_price, started_at):
        """Start tracking a job's charges; its price is fixed now, at its start (design section 9)."""
        with self.db.cursor() as c:
            # Already tracked: leave it. (Not INSERT IGNORE, which also hides values that don't fit.)
            c.execute("INSERT INTO job_charges (db_index, job_id, customer, username, partition_name, units, "
                      "unit_hour_price, started_at, state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'RUNNING') "
                      "ON DUPLICATE KEY UPDATE db_index=db_index",
                      (db_index, job_id, customer, username, partition, units, unit_hour_price, started_at))
        self.db.commit()

    def charge_job(self, db_index, elapsed_seconds, state, ended_at, operator, at=None):
        """Bring a job's charges up to `elapsed_seconds`, in one transaction with the job's record, so a
        crash can never charge the same minutes twice. Returns the amount charged now."""
        job = self.job(db_index)
        if job is None:
            raise billing.BillingError(f"job record {db_index} isn't tracked")
        at = at or utcnow()

        def work(c):
            c.execute("SELECT charged_seconds, charged, final FROM job_charges WHERE db_index=%s FOR UPDATE",
                      (db_index,))
            charged_seconds, charged, final = c.fetchone()
            if final:
                return 0
            target = max(charged_seconds, elapsed_seconds)
            due = billing.job_cost(job["units"], target, job["unit_hour_price"]) - charged
            if due > 0:
                note = f"job {job['job_id']} ({job['username']}, {job['partition_name']}): {target // 60} min"
                self._debit_in(c, job["customer"], "charge", due, f"job:{db_index}:{target}", note, operator, at)
            c.execute("UPDATE job_charges SET charged_seconds=%s, charged=%s, state=%s, ended_at=%s, final=%s "
                      "WHERE db_index=%s", (target, charged + max(due, 0), state, ended_at, 1 if ended_at else 0,
                                            db_index))
            return max(due, 0)

        return self._in_transaction(job["customer"], work)

    def refund_job(self, db_index, reason, operator, at=None):
        """Give back everything a job was charged (node failure, or an admin's decision), as a new batch.
        Returns the amount refunded (0 if nothing to refund or already refunded)."""
        job = self.job(db_index)
        if job is None:
            raise billing.BillingError(f"job record {db_index} isn't tracked")
        at = at or utcnow()

        def work(c):
            c.execute("SELECT charged, refunded FROM job_charges WHERE db_index=%s FOR UPDATE", (db_index,))
            charged, refunded = c.fetchone()
            if refunded or charged <= 0:
                return 0
            entry = self._insert(c, job["customer"], "refund", charged, f"refund:job:{db_index}",
                                 f"job {job['job_id']}: {reason}", operator, at)
            c.execute("INSERT INTO batches VALUES (%s,%s,%s,%s)",
                      (entry, job["customer"], charged, billing.new_batch_expiry(at)))
            self._settle_debt(c, job["customer"], entry, charged)
            c.execute("UPDATE job_charges SET refunded=1 WHERE db_index=%s", (db_index,))
            return charged

        return self._in_transaction(job["customer"], work)

    def mark_graced(self, db_index):
        with self.db.cursor() as c:
            c.execute("UPDATE job_charges SET graced=1 WHERE db_index=%s", (db_index,))
        self.db.commit()

    def running_jobs(self, customer):
        with self.db.cursor(pymysql.cursors.DictCursor) as c:
            c.execute("SELECT * FROM job_charges WHERE customer=%s AND final=0", (customer,))
            rows = c.fetchall()
        self.db.rollback()
        return list(rows)

    def jobs_for(self, customer, username, month):
        """A customer's jobs that started in a month ("2026-10"), or only one user's."""
        start = datetime.datetime.strptime(month + "-01", "%Y-%m-%d")
        end = (start + datetime.timedelta(days=32)).replace(day=1)
        sql = "SELECT * FROM job_charges WHERE customer=%s AND started_at >= %s AND started_at < %s"
        args = [customer, start, end]
        if username:
            sql += " AND username=%s"
            args.append(username)
        with self.db.cursor(pymysql.cursors.DictCursor) as c:
            c.execute(sql + " ORDER BY started_at", args)
            rows = c.fetchall()
        self.db.rollback()
        return list(rows)

    # --- storage ------------------------------------------------------------------------------------

    def record_storage(self, customer, used_bytes, gb_month_price, operator, at=None):
        """An hourly reading, which charges for any new monthly peak, in one transaction.
        Returns the amount charged now."""
        at = at or utcnow()
        month = at.strftime("%Y-%m")

        def work(c):
            c.execute("INSERT INTO storage_readings VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE customer=customer",
                      (customer, at, used_bytes))
            c.execute("SELECT peak_bytes, gb_month_price FROM storage_months WHERE customer=%s AND month=%s "
                      "FOR UPDATE", (customer, month))
            row = c.fetchone()
            if row is None:
                peak, price = 0, gb_month_price          # the month's price is fixed at its first reading
                c.execute("INSERT INTO storage_months VALUES (%s,%s,0,%s)", (customer, month, price))
            else:
                peak, price = int(row[0]), int(row[1])
            new_peak, _ = billing.storage_increment(peak, used_bytes)
            cost = billing.storage_cost(new_peak, price) - billing.storage_cost(peak, price)
            if new_peak != peak:
                c.execute("UPDATE storage_months SET peak_bytes=%s WHERE customer=%s AND month=%s",
                          (new_peak, customer, month))
            if cost > 0:
                self._debit_in(c, customer, "storage", cost, f"storage:{month}:{new_peak}",
                               f"storage {month}: new peak {new_peak / billing.GIB:.2f} GiB", operator, at)
            return max(cost, 0)

        return self._in_transaction(customer, work)

    def storage_month(self, customer, month):
        with self.db.cursor() as c:
            c.execute("SELECT peak_bytes, gb_month_price FROM storage_months WHERE customer=%s AND month=%s",
                      (customer, month))
            row = c.fetchone()
            c.execute("SELECT used_bytes, at FROM storage_readings WHERE customer=%s ORDER BY at DESC LIMIT 1",
                      (customer,))
            latest = c.fetchone()
        self.db.rollback()
        return {"peak_bytes": int(row[0]) if row else 0, "gb_month_price": int(row[1]) if row else None,
                "latest_bytes": int(latest[0]) if latest else None, "latest_at": latest[1] if latest else None}

    # --- prices -------------------------------------------------------------------------------------

    def prices_at(self, customer, when):
        with self.db.cursor() as c:
            c.execute("SELECT prices FROM price_history WHERE customer=%s AND effective_from <= %s "
                      "ORDER BY effective_from DESC, id DESC LIMIT 1", (customer, when))
            row = c.fetchone()
        self.db.rollback()
        return json.loads(row[0]) if row else None

    def record_prices(self, customer, prices, effective_from):
        """Note a customer's prices if they differ from the latest recorded ones. Returns True if new."""
        with self.db.cursor() as c:
            c.execute("SELECT prices FROM price_history WHERE customer=%s ORDER BY effective_from DESC, id DESC "
                      "LIMIT 1", (customer,))
            row = c.fetchone()
            if row and json.loads(row[0]) == prices:
                self.db.rollback()
                return False
            c.execute("INSERT INTO price_history (customer, effective_from, prices) VALUES (%s,%s,%s)",
                      (customer, effective_from, json.dumps(prices, sort_keys=True)))
        self.db.commit()
        return True

    def price_history(self, customer):
        with self.db.cursor() as c:
            c.execute("SELECT effective_from, prices FROM price_history WHERE customer=%s ORDER BY effective_from, id",
                      (customer,))
            rows = c.fetchall()
        self.db.rollback()
        return [(r[0], json.loads(r[1])) for r in rows]
