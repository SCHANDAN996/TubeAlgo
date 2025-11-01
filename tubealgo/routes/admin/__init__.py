# tubealgo/routes/admin/__init__.py

from flask import Blueprint

# Create main admin blueprint
admin_bp = Blueprint('admin', __name__, template_folder='../../templates/admin')

# Import sub-modules AFTER blueprint creation to avoid circular imports
from . import dashboard, users, monetization, system

# All routes are now registered through the sub-modules