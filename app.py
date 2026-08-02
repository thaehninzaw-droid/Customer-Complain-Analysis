from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

client = MongoClient("mongodb://localhost:27017/")
db = client["ComcastDB"]
users = db["users"]


@app.route("/")
def home():
    return "MongoDB Connected!"


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json

    name = data["name"]
    email = data["email"]
    password = data["password"]

    # Check if email already exists
    if users.find_one({"email": email}):
        return jsonify({"message": "Email already exists"}), 400

    users.insert_one({
        "name": name,
        "email": email,
        "password": password
    })

    return jsonify({"message": "Signup Successful"})


# ---------------- LOGIN ----------------
@app.route("/login", methods=["POST"])
def login():
    data = request.json

    email = data["email"]
    password = data["password"]

    # Check if the user exists
    user = users.find_one({
        "email": email,
        "password": password
    })

    if user:
        return jsonify({
            "message": "Login Successful",
            "name": user["name"]
        })

    return jsonify({
        "message": "Invalid email or password"
    }), 401


if __name__ == "__main__":
    app.run(debug=True)