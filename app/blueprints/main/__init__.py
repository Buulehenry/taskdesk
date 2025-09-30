from flask import Blueprint

main_bp = Blueprint("main", __name__)

# Import route modules to register their endpoints
from . import routes
from . import routes_subscribe
from  . import rating
from . import careers
