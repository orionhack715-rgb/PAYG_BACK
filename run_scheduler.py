import os
import time

from dotenv import load_dotenv

from app import create_app


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

os.environ["SCHEDULER_ENABLED"] = "true"
app = create_app(os.getenv("FLASK_ENV", "development"))


if __name__ == "__main__":
    app.logger.info("Dedicated scheduler process started.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        app.logger.info("Dedicated scheduler process stopped.")
