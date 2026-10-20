"""The money logic of billing and credits (slurm-design.md section 9), with no database or Slurm in it,
so all of it is covered by code tests (tests/code/test_billing.py).

Amounts are whole numbers of micro-credits (1 credit = 1,000,000), never floating point. 1 credit is
worth 1 US dollar (plan D40, working assumption). Customers see amounts rounded to cents.
"""

import datetime
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MICRO = 1_000_000
GIB = 1024 ** 3
CREDIT_LIFETIME_DAYS = 365          # credits expire 12 months after purchase (design Q7)
GRACE_MINUTES = 10                  # a running job's extra time when its customer runs out (design 9)
PRICE_KEYS = ("cpu_core_hour", "storage_gb_month")


class BillingError(Exception):
    pass


# --- money ------------------------------------------------------------------------------------------

def to_micro(value):
    """Credits (a number or text like "12.50") as micro-credits. More than 6 decimals is refused."""
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        raise BillingError(f"not an amount: {value!r}") from None
    micro = d * MICRO
    if micro != micro.to_integral_value():
        raise BillingError(f"too many decimals: {value}")
    return int(micro)


def show(micro):
    """Micro-credits as credits with two decimals, rounded half up: "12.35". Never "-0.00"."""
    rounded = (Decimal(micro) / MICRO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(rounded if rounded != 0 else Decimal("0.00"))


# --- prices -----------------------------------------------------------------------------------------

def _as_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def check_rates(rates):
    """Problems in config/rates.yml, as a list of sentences."""
    found = []
    if not isinstance(rates.get("units_per_gpu"), int) or rates["units_per_gpu"] < 1:
        found.append("units_per_gpu must be a whole number, at least 1")
    partitions = rates.get("partitions") or {}
    prices = rates.get("prices") or []
    if not prices:
        found.append("prices: needs at least one entry")
    last = None
    for i, entry in enumerate(prices):
        where = f"prices entry {i + 1}"
        try:
            when = _as_date(entry.get("from"))
        except (TypeError, ValueError):
            found.append(f"{where}: 'from' must be a date like 2026-10-01")
            continue
        if last and when <= last:
            found.append(f"{where}: dates must go up")
        last = when
        for key in PRICE_KEYS:
            if key not in entry:
                found.append(f"{where}: missing {key}")
        models = entry.get("gpu_hour") or {}
        for partition, model in partitions.items():
            if model not in models:
                found.append(f"{where}: no gpu_hour price for {model} (partition {partition})")
        for value in [entry.get(k) for k in PRICE_KEYS] + list(models.values()):
            try:
                if value is not None and to_micro(value) < 0:
                    found.append(f"{where}: prices can't be negative")
            except BillingError as e:
                found.append(f"{where}: {e}")
    return found


def default_prices_at(rates, when):
    """The default price list in effect on a date: {"gpu_hour": {model: micro}, key: micro, ...}."""
    day = _as_date(when)
    chosen = None
    for entry in rates["prices"]:
        if _as_date(entry["from"]) <= day:
            chosen = entry
    if chosen is None:
        raise BillingError(f"no prices in effect on {day}")
    return {"gpu_hour": {m: to_micro(v) for m, v in chosen["gpu_hour"].items()},
            **{k: to_micro(chosen[k]) for k in PRICE_KEYS}}


def customer_prices(defaults, customer):
    """A customer's prices: the default list, less their discount, with their own prices on top.
    customer["rates"] keys: "gpu_hour.<model>", "cpu_core_hour", "storage_gb_month"."""
    discount = customer.get("discount_percent", 0)
    if not isinstance(discount, int) or not 0 <= discount <= 100:
        raise BillingError("discount_percent must be a whole number from 0 to 100")

    def discounted(micro):
        return micro * (100 - discount) // 100

    prices = {"gpu_hour": {m: discounted(v) for m, v in defaults["gpu_hour"].items()},
              **{k: discounted(defaults[k]) for k in PRICE_KEYS}}
    for key, value in (customer.get("rates") or {}).items():
        if key.startswith("gpu_hour."):
            model = key.split(".", 1)[1]
            if model not in prices["gpu_hour"]:
                raise BillingError(f"rates: no GPU model '{model}' in the default price list")
            prices["gpu_hour"][model] = to_micro(value)
        elif key in PRICE_KEYS:
            prices[key] = to_micro(value)
        else:
            raise BillingError(f"rates: unknown price '{key}'")
    return prices


def unit_hour_price(prices, rates, partition):
    """Micro-credits per Slurm billing unit per hour on a partition.
    GPU partitions: a GPU share is units_per_gpu units. Other partitions: 1 unit = 1 hardware thread,
    so a core (2 threads) costs cpu_core_hour."""
    model = (rates.get("partitions") or {}).get(partition)
    if model:
        return prices["gpu_hour"][model] // rates["units_per_gpu"]
    return prices["cpu_core_hour"] // 2


def highest_unit_hour_price(prices, rates, partitions):
    return max(unit_hour_price(prices, rates, p) for p in partitions)


# --- jobs -------------------------------------------------------------------------------------------

def job_cost(units, seconds, unit_hour_micro):
    """What a job has cost after `seconds`, in micro-credits (rounded down, so never overcharged)."""
    return units * seconds * unit_hour_micro // 3600


# --- credit batches ---------------------------------------------------------------------------------

@dataclass
class Batch:
    id: int
    amount: int                       # micro-credits bought or granted
    expires_at: datetime.datetime
    used: int = 0                     # spent from it so far
    expired: int = 0                  # written off when it expired

    @property
    def remaining(self):
        return self.amount - self.used - self.expired


def new_batch_expiry(created_at):
    return created_at + datetime.timedelta(days=CREDIT_LIFETIME_DAYS)


def spend(batches, amount, at):
    """Take `amount` from the batches that expire soonest first (FIFO by expiry). Batches already
    expired at `at` are skipped. Returns ([(batch id, amount taken)], what no batch could cover).
    The batches are updated in place."""
    left = amount
    taken = []
    for b in sorted(batches, key=lambda b: (b.expires_at, b.id)):
        if left <= 0:
            break
        if b.expires_at <= at or b.remaining <= 0:
            continue
        part = min(b.remaining, left)
        b.used += part
        left -= part
        taken.append((b.id, part))
    return taken, left


def expire(batches, now):
    """Batches past their expiry with credit left: [(batch id, amount that expires)]. Updated in place."""
    out = []
    for b in sorted(batches, key=lambda b: (b.expires_at, b.id)):
        if b.expires_at <= now and b.remaining > 0:
            out.append((b.id, b.remaining))
            b.expired += b.remaining
    return out


def available(batches, debt, now):
    """Credit a customer can still spend: what's left in unexpired batches, less unpaid charges."""
    return sum(b.remaining for b in batches if b.expires_at > now) - debt


# --- storage ----------------------------------------------------------------------------------------

def storage_increment(month_peak_bytes, reading_bytes):
    """A new reading only costs anything if it's above the month's peak so far.
    Returns (new peak, bytes to charge for)."""
    if reading_bytes > month_peak_bytes:
        return reading_bytes, reading_bytes - month_peak_bytes
    return month_peak_bytes, 0


def storage_cost(nbytes, gb_month_micro):
    """Micro-credits for `nbytes` of month peak at a price per GiB-month (rounded down)."""
    return nbytes * gb_month_micro // GIB


# --- Slurm enforcement ------------------------------------------------------------------------------

def qos_limit(used_unit_minutes, available_micro, unit_hour_micro):
    """GrpTRESMins=billing for a customer's QOS. Slurm compares it with the QOS's lifetime usage, so the
    limit is what's been used plus what the available credit still buys (review W1)."""
    if unit_hour_micro <= 0:
        raise BillingError("a price of zero can't be enforced this way")
    affordable = max(0, available_micro) * 60 // unit_hour_micro
    return used_unit_minutes + affordable


@dataclass
class RunningJob:
    job_id: str
    elapsed_seconds: int
    time_limit_minutes: int
    graced: bool = False


def grace_updates(available_micro, jobs):
    """When a customer has nothing left, each running job gets GRACE_MINUTES more, once.
    Returns [(job id, new time limit in minutes)] for jobs whose limit should be shortened."""
    if available_micro > 0:
        return []
    out = []
    for job in jobs:
        if job.graced:
            continue
        new_limit = -(-job.elapsed_seconds // 60) + GRACE_MINUTES     # minutes so far, rounded up, + grace
        if new_limit < job.time_limit_minutes:
            out.append((job.job_id, new_limit))
    return out


@dataclass
class Statement:
    opening: int
    topups: int = 0
    grants: int = 0
    refunds: int = 0
    charges: int = 0
    storage: int = 0
    expiries: int = 0
    adjustments: int = 0
    lines: list = field(default_factory=list)

    @property
    def closing(self):
        return (self.opening + self.topups + self.grants + self.refunds + self.adjustments
                - self.charges - self.storage - self.expiries)


def compare_charges(expected, charged):
    """The monthly cross-check (plan 12.3). expected and charged: {job record: micro-credits}, for
    finished jobs. Returns a list of differences; empty means the ledger agrees with Slurm."""
    out = []
    for key in sorted(set(expected) | set(charged)):
        want, have = expected.get(key), charged.get(key)
        if want is None:
            out.append(f"job record {key}: charged {show(have)} but Slurm has no such finished job")
        elif have is None:
            out.append(f"job record {key}: Slurm says it cost {show(want)} but it was never charged")
        elif want != have:
            out.append(f"job record {key}: charged {show(have)}, Slurm says {show(want)}")
    return out

