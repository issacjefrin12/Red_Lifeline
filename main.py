import uvicorn
from asgiref.wsgi import WsgiToAsgi
from app import app as flask_app

app = WsgiToAsgi(flask_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
