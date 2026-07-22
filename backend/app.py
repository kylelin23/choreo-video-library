import os
from flask import Flask
from flask_cors import CORS
from flask_session import Session
from dotenv import load_dotenv
from routes.auth import auth_bp

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]
app.config["SESSION_TYPE"] = "filesystem"
Session(app)
CORS(app, supports_credentials=True, origins=["http://localhost:5173"])

app.register_blueprint(auth_bp)

if __name__ == '__main__':
    app.run(debug=True)
