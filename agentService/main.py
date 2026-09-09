from flask_app import app
from agent_runtime import load_runtime_config


if __name__ == "__main__":
    config = load_runtime_config()
    app.run(host=config.flask_host, port=config.flask_port, debug=config.flask_debug)