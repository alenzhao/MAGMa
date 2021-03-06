"""Fill reactionsequence

Revision ID: 14322145f9b5
Revises: 28182dc2d089
Create Date: 2014-01-03 10:10:32.558457

"""
from alembic import op
from sqlalchemy.orm.session import sessionmaker
from magmaweb.models import fill_molecules_reactions

# revision identifiers, used by Alembic.
revision = '14322145f9b5'
down_revision = '28182dc2d089'


def upgrade():
    connection = op.get_bind()
    Session = sessionmaker(bind=connection)
    fill_molecules_reactions(Session())


def downgrade():
    pass
