"""initial migration

Revision ID: 7de1feafc502
Revises: 02bf99f5a573
Create Date: 2024-11-02 12:04:42.455213

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7de1feafc502'
down_revision = '02bf99f5a573'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('password_hash',
               existing_type=sa.VARCHAR(length=128),
               type_=sa.String(length=256),
               existing_nullable=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('password_hash',
               existing_type=sa.String(length=256),
               type_=sa.VARCHAR(length=128),
               existing_nullable=True)

    # ### end Alembic commands ###
