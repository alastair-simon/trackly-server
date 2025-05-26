from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config.config import config

db = SQLAlchemy()
migrate = Migrate()

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    from app.api.search import search_bp
    app.register_blueprint(search_bp, url_prefix='/api')

    #todo: remove for production
    @app.route('/')
    def root():
        return 'server running...'

    return app