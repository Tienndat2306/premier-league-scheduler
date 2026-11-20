from flask import Flask
import os


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )
    app.config["SECRET_KEY"] = "epl-scheduler-secret-key"

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
