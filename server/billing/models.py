"""Request models for the billing module (Pydantic v2)."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

CUSTOMER_STATUS = ("active", "frozen", "closed")
TICKET_STATUS = ("open", "in_progress", "resolved", "closed")
TICKET_PRIORITY = ("low", "medium", "high", "critical")
EMPLOYEE_ROLE = ("admin", "manager", "support")
CHARGE_STATUS = ("draft", "issued", "paid", "cancelled")
LINE_KIND = ("product", "light", "service", "hours", "manual", "usage")
EXPENSE_CATEGORY = ("software", "database", "staff", "equipment", "office", "infra", "other")
CURRENCIES = ("ILS", "USD", "EUR")
SUBSCRIPTION_KIND = ("product", "service")


class CustomerIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=40)
    contact_person: str = Field(default="", max_length=120)
    address: str = Field(default="", max_length=300)
    status: str = "active"
    bill_hours: bool = False
    hourly_rate: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    client_id: Optional[str] = None
    notes: str = Field(default="", max_length=2000)
    payment_method: str = Field(default="", max_length=80)
    vat_id: str = Field(default="", max_length=40)


class CustomerPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    email: Optional[str] = None
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    bill_hours: Optional[bool] = None
    hourly_rate: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    client_id: Optional[str] = None          # "" clears
    notes: Optional[str] = None
    payment_method: Optional[str] = None
    vat_id: Optional[str] = None


class ProductIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    price: float = Field(default=0, ge=0, allow_inf_nan=False)
    has_light_user: bool = False
    light_user_price: float = Field(default=0, ge=0, allow_inf_nan=False)
    project_id: Optional[str] = None
    features: list[str] = Field(default_factory=list)


class ProductPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    has_light_user: Optional[bool] = None
    light_user_price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    project_id: Optional[str] = None
    features: Optional[list[str]] = None


class ServiceIn(BaseModel):
    workspace_id: str
    description: str = Field(min_length=1, max_length=300)
    price: float = Field(default=0, ge=0, allow_inf_nan=False)
    recurring: bool = False


class ServicePatch(BaseModel):
    description: Optional[str] = Field(default=None, min_length=1, max_length=300)
    price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    recurring: Optional[bool] = None


class SubscriptionIn(BaseModel):
    customer_id: str
    kind: str = "product"
    product_id: Optional[str] = None
    service_id: Optional[str] = None
    user_count: int = Field(default=0, ge=0)
    light_user_count: int = Field(default=0, ge=0)
    quantity: float = Field(default=1, ge=0, allow_inf_nan=False)
    valid_from: Optional[str] = None       # YYYY-MM-DD, default today
    valid_until: Optional[str] = None


class SubscriptionPatch(BaseModel):
    user_count: Optional[int] = Field(default=None, ge=0)
    light_user_count: Optional[int] = Field(default=None, ge=0)
    quantity: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None      # "" clears


class EmployeeIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=40)
    position: str = Field(default="", max_length=80)
    role: str = "support"
    hourly_rate: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    user_id: Optional[str] = None
    active: bool = True


class EmployeePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    role: Optional[str] = None
    hourly_rate: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    user_id: Optional[str] = None            # "" clears
    active: Optional[bool] = None


class TicketIn(BaseModel):
    workspace_id: str
    customer_id: str
    product_id: Optional[str] = None
    employee_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    status: str = "open"
    priority: str = "medium"
    contact_person: str = Field(default="", max_length=120)
    contact_phone: str = Field(default="", max_length=40)
    group_name: str = Field(default="", max_length=120)
    image_url: str = Field(default="", max_length=600)
    opened_at: Optional[str] = None
    initial_minutes: int = Field(default=0, ge=0)   # convenience: first time entry
    initial_note: str = Field(default="", max_length=2000)


class TicketPatch(BaseModel):
    customer_id: Optional[str] = None
    product_id: Optional[str] = None
    employee_id: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    group_name: Optional[str] = None
    image_url: Optional[str] = None
    opened_at: Optional[str] = None


class TimeEntryIn(BaseModel):
    employee_id: Optional[str] = None
    description: str = Field(default="", max_length=2000)
    minutes: int = Field(ge=0, le=24 * 60)
    entry_date: Optional[str] = None


class TimeEntryPatch(BaseModel):
    employee_id: Optional[str] = None
    description: Optional[str] = None
    minutes: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    entry_date: Optional[str] = None


class ExternalUpdateIn(BaseModel):
    contact_name: str = Field(min_length=1, max_length=120)
    contact_phone: str = Field(default="", max_length=40)
    content: str = Field(min_length=1, max_length=4000)
    minutes: Optional[int] = Field(default=None, ge=0, le=24 * 60)
    update_date: Optional[str] = None


class GenerateIn(BaseModel):
    workspace_id: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")   # YYYY-MM
    customer_id: Optional[str] = None                        # one customer only


class ChargePatch(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    vat_pct: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    paid_at: Optional[str] = None


class ChargeLineIn(BaseModel):
    kind: str = "manual"
    description: str = Field(min_length=1, max_length=300)
    quantity: float = Field(default=1, allow_inf_nan=False)
    unit_price: float = Field(default=0, allow_inf_nan=False)


class ManualChargeIn(BaseModel):
    workspace_id: str
    customer_id: str
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    lines: list[ChargeLineIn] = Field(default_factory=list)
    notes: str = ""


class ExpenseIn(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1, max_length=200)
    amount: float = Field(ge=0, allow_inf_nan=False)
    currency: str = "ILS"
    category: str = "other"
    expense_date: Optional[str] = None
    description: str = Field(default="", max_length=2000)
    recurring: bool = False
    rate: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)   # manual FX override


class ExpensePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Optional[str] = None
    category: Optional[str] = None
    expense_date: Optional[str] = None
    description: Optional[str] = None
    recurring: Optional[bool] = None
    rate: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)


class KnowledgeIn(BaseModel):
    workspace_id: str
    product_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=50000)
    category: str = Field(default="", max_length=80)
    tags: list[str] = Field(default_factory=list)


class KnowledgePatch(BaseModel):
    product_id: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None


class FxRateIn(BaseModel):
    currency: str
    rate_date: str
    rate: float = Field(gt=0, allow_inf_nan=False)


class SettingsIn(BaseModel):
    vat_pct: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    hourly_rate: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Optional[str] = None
    ticket_prefix: Optional[str] = Field(default=None, max_length=10)
    business: Optional[dict[str, Any]] = None     # name, address, vat_id, phone, email
    fx_defaults: Optional[dict[str, float]] = None  # USD: 3.7, EUR: 4.0


class ImportIn(BaseModel):
    """Bulk import from the old system (scripts/import_billing.py). Each list
    holds rows in the old column names; ids are mapped through legacy_id."""
    workspace_id: str
    customers: list[dict[str, Any]] = Field(default_factory=list)
    products: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    product_users: list[dict[str, Any]] = Field(default_factory=list)
    employees: list[dict[str, Any]] = Field(default_factory=list)
    service_tickets: list[dict[str, Any]] = Field(default_factory=list)
    service_time_entries: list[dict[str, Any]] = Field(default_factory=list)
    external_ticket_updates: list[dict[str, Any]] = Field(default_factory=list)
    monthly_summaries: list[dict[str, Any]] = Field(default_factory=list)
    billing_items: list[dict[str, Any]] = Field(default_factory=list)
    expenses: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_items: list[dict[str, Any]] = Field(default_factory=list)
