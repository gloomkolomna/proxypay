"""initial: orders, webhook_deliveries, games, gateway_logs, gateway_settings

Revision ID: 0001
Revises:
Create Date: 2026-08-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("game_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description_prefix", sa.String(), server_default=""),
        sa.Column("webhook_url", sa.String(), nullable=False),
        sa.Column("success_url", sa.String(), nullable=False),
        sa.Column("fail_url", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False),
        sa.Column("webhook_secret", sa.String(), nullable=False),
        sa.Column("tax_code", sa.String(), server_default="1105"),
        sa.Column("payment_method", sa.String(), server_default="full_payment"),
        sa.Column("payment_object", sa.String(), server_default="commodity"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.String(), server_default=""),
        sa.Column("updated_at", sa.String(), server_default=""),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("game_id", sa.String(), nullable=False),
        sa.Column("vk_id", sa.Integer(), nullable=False),
        sa.Column("amount_kop", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("receipt_email", sa.String(), nullable=True),
        sa.Column("receipt_items_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending"),
        sa.Column("moneta_operation_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), server_default=""),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.Column("expires_at", sa.String(), nullable=True),
    )
    op.create_index("ix_orders_transaction_id", "orders", ["transaction_id"], unique=True)
    op.create_index("ix_orders_game_id", "orders", ["game_id"])
    op.create_index("ix_orders_vk_id", "orders", ["vk_id"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Integer(),
                  sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(length=20), server_default="queued"),
        sa.Column("last_response_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), server_default=""),
        sa.Column("next_retry_at", sa.String(), nullable=True),
        sa.Column("delivered_at", sa.String(), nullable=True),
    )
    op.create_index("ix_webhook_deliveries_order_id",
                    "webhook_deliveries", ["order_id"])
    op.create_table(
        "gateway_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("game_id", sa.String(), nullable=True),
        sa.Column("actor_vk_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), server_default=""),
        sa.Column("created_at", sa.String(), server_default=""),
    )
    op.create_index("ix_gateway_logs_event", "gateway_logs", ["event"])
    op.create_index("ix_gateway_logs_transaction_id", "gateway_logs", ["transaction_id"])
    op.create_index("ix_gateway_logs_game_id", "gateway_logs", ["game_id"])
    op.create_index("ix_gateway_logs_created_at", "gateway_logs", ["created_at"])
    op.create_table(
        "gateway_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), server_default=""),
        sa.Column("updated_at", sa.String(), server_default=""),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gateway_settings")
    op.drop_index("ix_gateway_logs_created_at", table_name="gateway_logs")
    op.drop_index("ix_gateway_logs_game_id", table_name="gateway_logs")
    op.drop_index("ix_gateway_logs_transaction_id", table_name="gateway_logs")
    op.drop_index("ix_gateway_logs_event", table_name="gateway_logs")
    op.drop_table("gateway_logs")
    op.drop_index("ix_webhook_deliveries_order_id", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_orders_vk_id", table_name="orders")
    op.drop_index("ix_orders_game_id", table_name="orders")
    op.drop_index("ix_orders_transaction_id", table_name="orders")
    op.drop_table("orders")
    op.drop_table("games")
