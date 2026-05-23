import uvicorn
from asgiref.wsgi import WsgiToAsgi
from app import app as flask_app, init_db
import os

# Ensure schema bootstrap runs in container deployments too.
if os.getenv("BBMS_AUTO_INIT_DB", "true").lower() == "true":
    init_db()

app = WsgiToAsgi(flask_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
