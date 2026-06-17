from app import create_app

app = create_app()

import os

if __name__ == '__main__':
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "t")
    app.run(host='0.0.0.0', debug=debug_mode, port=5001)
