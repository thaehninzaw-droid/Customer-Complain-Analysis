from pymongo import MongoClient

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")

# Create database
db = client["ComcastDB"]

# Create collection
collection = db["complaints"]

print("MongoDB connected successfully!")