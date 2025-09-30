from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

app = create_app()
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_for=1, x_host=1, x_port=1, x_prefix=1)
