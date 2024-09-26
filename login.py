import streamlit as st
from pymongo import MongoClient
from google.cloud import vision
import io
import hashlib
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Vision API client with API key
import google.auth
from google.cloud import vision_v1
from google.oauth2 import service_account

# Load credentials
credentials = service_account.Credentials.from_service_account_info({
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key_id": "your-private-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nYOUR_PRIVATE_KEY\n-----END PRIVATE KEY-----\n",
    "client_email": "your-client-email",
    "client_id": "your-client-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/identitytoolkit/v3/relyingparty/publicKeys"
})

# Initialize Vision API client
client = vision_v1.ImageAnnotatorClient(credentials=credentials)

# Connect to MongoDB
client_mongo = MongoClient("mongodb+srv://kutushlahiri:SIH1234@cluster0.zn1hj.mongodb.net/?retryWrites=true&w=majority")
db = client_mongo['Health']
customer_collection = db['customer']

# Hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Function to authenticate user
def login_user(email, password):
    hashed_password = hash_password(password)
    user = customer_collection.find_one({"email": email, "password": hashed_password})
    return user

# Function to upload and process image using Google Vision API
def process_image(file):
    # Load the image from the file
    content = file.read()
    image = vision.Image(content=content)

    # Perform text detection
    response = client.text_detection(image=image)
    texts = response.text_annotations

    # Extract detected text
    if texts:
        detected_text = texts[0].description
        return detected_text
    else:
        return "No text detected"

# Registration and login logic
st.title("User Registration and Login")

# Login form
st.subheader("Login")
email = st.text_input("Email")
password = st.text_input("Password", type="password")
login_button = st.button("Login")

if login_button:
    user = login_user(email, password)
    if user:
        st.success(f"Welcome, {user['name']}!")
        
        # Once logged in, provide image upload option
        st.subheader("Upload Food Label Image")
        uploaded_file = st.file_uploader("Choose an image file", type=["jpg", "jpeg", "png"])
        
        if uploaded_file:
            # Process the uploaded image with Vision API
            detected_text = process_image(uploaded_file)
            st.write("Detected Text from Image:")
            st.write(detected_text)
    else:
        st.error("Invalid email or password.")
