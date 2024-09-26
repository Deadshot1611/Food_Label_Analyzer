import streamlit as st
from pymongo import MongoClient
import hashlib
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to MongoDB
client = MongoClient(os.getenv("MONGODB_URI"))
db = client.Health
customer_collection = db.customer

# Function to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def calculate_bmi(weight, height):
    height_in_meters = height / 100
    bmi = weight / (height_in_meters ** 2)
    return round(bmi, 2)
# Streamlit UI for user registration
st.title("User Registration")

with st.form("registration_form"):
    st.subheader("Register a New Account")

    name = st.text_input("Name *", key="register_name")
    email = st.text_input("Email *", key="register_email")
    password = st.text_input("Password *", type="password", key="register_password")
    confirm_password = st.text_input("Confirm Password *", type="password", key="confirm_password")
    age = st.number_input("Age *", min_value=1, max_value=120, key="register_age")
    height = st.number_input("Height (in cm) *", min_value=50, max_value=250, key="register_height")
    weight = st.number_input("Weight (in kg) *", min_value=10, max_value=300, key="register_weight")
    allergies = st.text_input("Allergies (if any)", key="register_allergies")
    health_conditions = st.text_input("Health Conditions (if any)", key="register_health_conditions")
    activity_level = st.selectbox("Activity Level", ["Low", "Moderate", "High"], key="register_activity_level")
    dietary_preferences = st.multiselect("Dietary Preferences", ["Vegetarian", "Vegan", "Gluten-Free", "Keto", "Paleo", "No preference"], key="register_dietary_preferences")
    health_goals = st.selectbox("Health Goals", ["Lose weight", "Gain muscle", "Maintain weight", "Improve stamina", "General well-being"], key="register_health_goals")

    submitted = st.form_submit_button("Register")

    if submitted:
        if password != confirm_password:
            st.error("Passwords do not match!")
        else:
            # Hash the password before storing it
            hashed_password = hash_password(password)
            user_data = {
                "name": name,
                "email": email,
                "password": hashed_password,
                "age": age,
                "height": height,
                "weight": weight,
                "bmi": calculate_bmi(weight, height),  # Assuming `calculate_bmi` is defined elsewhere
                "allergies": allergies,
                "health_conditions": health_conditions,
                "activity_level": activity_level,
                "dietary_preferences": dietary_preferences,
                "health_goals": health_goals
            }
            
            # Insert user data into MongoDB
            customer_collection.insert_one(user_data)
            st.success(f"Registration successful! Your BMI is {user_data['bmi']}.")
