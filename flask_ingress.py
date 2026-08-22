"""Entry point. Run with: python flask_ingress.py"""
import logging
from dotenv import load_dotenv
load_dotenv()

from app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5005, debug=False)
