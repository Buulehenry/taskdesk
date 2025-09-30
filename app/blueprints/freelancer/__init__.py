from flask import Blueprint


freelancer_bp = Blueprint('freelancer', __name__)


from . import routes  # noqa
