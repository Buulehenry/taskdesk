from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

# Import route modules to register their endpoints
from . import files          # noqa: E402,F401
from . import inbox          # noqa: E402,F401
from . import tasks_triage   # noqa: E402,F401
from . import quotes         # noqa: E402,F401
from . import assignments    # noqa: E402,F401
from . import tasks_bulk     # noqa: E402,F401
from . import tasks_notes    # noqa: E402,F401
from . import users_list_detail  # noqa: E402,F401
from . import users_actions      # noqa: E402,F401
from . import kyc               # noqa: E402,F401
from . import meetings 
from . import support
from . import marketing
from . import routes_ratings
from . import careers
