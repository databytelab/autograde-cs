"""grade total override

Revision ID: b7e4c2a9f1d3
Revises: 07f1debe3df8
Create Date: 2026-09-21 10:00:00.000000

Adds a single nullable column that lets a professor set a submission's final
score directly, bypassing the per-criterion breakdown. This is what makes a
manually-graded submission (e.g. one whose HTML converted badly and had to be
read by hand) enterable as one number instead of section by section. When it
is set it wins over the criterion scores; when it is NULL the score is
computed from the criteria as before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e4c2a9f1d3'
down_revision: Union[str, None] = '07f1debe3df8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('grade_results', schema=None) as batch_op:
        # Nullable, no server default: existing rows keep NULL, which means
        # "no manual total - compute from the criteria", exactly the current
        # behaviour.
        batch_op.add_column(sa.Column('total_override', sa.Numeric(6, 2),
                                      nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('grade_results', schema=None) as batch_op:
        batch_op.drop_column('total_override')
