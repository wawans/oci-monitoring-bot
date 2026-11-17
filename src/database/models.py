"""SQLAlchemy ORM models for OCI Multi-Account Monitoring Bot."""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return current UTC datetime with timezone awareness."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""


class Account(Base):
    """OCI Account model storing synchronized metadata from accounts.yaml."""

    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, doc="Unique identifier matching accounts.yaml"
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, doc="Human-readable account display name"
    )
    account_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="FREE_TIER", doc="Account tier: PAYG or FREE_TIER"
    )
    region: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="Primary OCI region e.g. ap-singapore-1"
    )
    tenancy_ocid: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Tenancy OCID"
    )
    compartment_id: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Target compartment OCID"
    )
    monthly_budget: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False, doc="Budget threshold in USD"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, doc="Active monitoring status"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    instances: Mapped[List["InstanceState"]] = relationship(
        "InstanceState",
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    billing_snapshots: Mapped[List["BillingSnapshot"]] = relationship(
        "BillingSnapshot",
        back_populates="account",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Account(account_id='{self.account_id}', name='{self.name}', type='{self.account_type}')>"


class InstanceState(Base):
    """Latest observed state and cached network details of an OCI compute instance."""

    __tablename__ = "instance_state"

    instance_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, doc="OCI Instance OCID"
    )
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Parent account identifier",
    )
    region: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="OCI region where VM resides"
    )
    compartment_id: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Compartment OCID where VM resides"
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Instance display name"
    )
    shape: Mapped[str] = mapped_column(
        String(128), nullable=False, doc="Compute shape e.g. VM.Standard.A1.Flex"
    )
    public_ip: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, doc="Resolved Public IP from VNIC"
    )
    private_ip: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, doc="Resolved Private IP from VNIC"
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNKNOWN", doc="Current state: RUNNING, STOPPED, etc."
    )
    latest_cpu_percent: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, doc="Most recent CPU percentage (0-100)"
    )
    consecutive_high_cpu: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, doc="Consecutive polls with CPU > 85%"
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationships
    account: Mapped["Account"] = relationship("Account", back_populates="instances")
    metrics: Mapped[List["MetricsLog"]] = relationship(
        "MetricsLog",
        back_populates="instance",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<InstanceState(id='{self.instance_id}', name='{self.display_name}', state='{self.lifecycle_state}')>"


class MetricsLog(Base):
    """Historical telemetry log for compute instances."""

    __tablename__ = "metrics_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("instance_state.instance_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cpu_percent: Mapped[float] = mapped_column(
        Float, nullable=False, doc="CPU utilization percentage"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    # Relationship
    instance: Mapped["InstanceState"] = relationship("InstanceState", back_populates="metrics")

    __table_args__ = (
        Index("idx_metrics_instance_timestamp", "instance_id", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<MetricsLog(instance='{self.instance_id}', cpu={self.cpu_percent}%, ts={self.timestamp})>"


class BillingSnapshot(Base):
    """Historical record of periodic billing cost summaries."""

    __tablename__ = "billing_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, doc="Actual accumulated spend MTD"
    )
    currency: Mapped[str] = mapped_column(
        String(16), default="USD", nullable=False, doc="Billing currency"
    )
    billing_period: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True, doc="Billing cycle period (e.g. 2026-11)"
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    # Relationship
    account: Mapped["Account"] = relationship("Account", back_populates="billing_snapshots")

    __table_args__ = (
        Index("idx_billing_account_period", "account_id", "billing_period"),
    )

    def __repr__(self) -> str:
        return f"<BillingSnapshot(account='{self.account_id}', amount={self.amount} {self.currency}, period='{self.billing_period}')>"


class AuditLog(Base):
    """Audit trail for all power management actions executed via the Telegram bot."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, doc="Telegram User ID of operator"
    )
    account_id: Mapped[str] = mapped_column(
        String(64), nullable=False, doc="Target account identifier"
    )
    instance_id: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Target compute instance OCID"
    )
    action: Mapped[str] = mapped_column(
        String(32), nullable=False, doc="Action executed: START, STOP, REBOOT"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, doc="Execution outcome: SUCCESS or FAILED"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLog(user={self.user_id}, action='{self.action}', instance='{self.instance_id}', status='{self.status}')>"


class BotSetting(Base):
    """Dynamic key-value settings table modified at runtime (e.g. polling intervals)."""

    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(
        String(64), primary_key=True, doc="Setting configuration key"
    )
    value: Mapped[str] = mapped_column(
        String(255), nullable=False, doc="Configured setting value"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<BotSetting(key='{self.key}', value='{self.value}')>"
