"""Initial schema: ohlcv_bars, fundamentals, earnings.

Revision ID: 0001
Revises:
Create Date: 2026-05-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ohlcv_bars",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("bar_size", sa.String(20), nullable=False),
        sa.Column("what_to_show", sa.String(20), nullable=False),
        sa.Column("adjusted", sa.Integer, nullable=False, server_default="1"),
        sa.Column("bar_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("wap", sa.Float),
        sa.Column("bar_count", sa.Integer),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "symbol", "sec_type", "currency", "bar_size",
            "what_to_show", "adjusted", "bar_date",
            name="uq_ohlcv_bar",
        ),
    )
    op.create_index("ix_ohlcv_symbol_date", "ohlcv_bars", ["symbol", "bar_date"])

    op.create_table(
        "fundamentals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("xml_data", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "report_type", name="uq_fundamentals"),
    )

    op.create_table(
        "earnings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("sec_type", sa.String(10), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("xml_data", sa.Text, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", name="uq_earnings_symbol"),
    )


def downgrade() -> None:
    op.drop_table("earnings")
    op.drop_table("fundamentals")
    op.drop_index("ix_ohlcv_symbol_date", table_name="ohlcv_bars")
    op.drop_table("ohlcv_bars")