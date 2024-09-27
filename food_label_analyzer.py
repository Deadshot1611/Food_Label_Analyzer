import streamlit as st
from streamlit_option_menu import option_menu
import time
import base64
from pymongo import MongoClient
import hashlib
import os
import easyocr
import difflib
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.mistralai import MistralAI
from translate import Translator
from dotenv import load_dotenv
import re
from streamlit.components.v1 import html
import ast
import json
import uuid

# Connect to MongoDB
client = MongoClient(os.getenv("MONGODB_URI"))
db = client.Health
customer_collection = db.customer
product_collection = db.product

# Initialize OCR and LlamaIndex models
reader = easyocr.Reader(['en'])
embedding_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
llm = MistralAI(api_key=os.getenv("MISTRAL_API_KEY"))

# Set the embedding model and LLM globally
Settings.embed_model = embedding_model
Settings.llm = llm

# Function to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Function to check hashed passwords
def check_password(stored_password, provided_password):
    return stored_password == hash_password(provided_password)

# Function to calculate BMI
def calculate_bmi(weight, height):
    height_in_meters = height / 100
    bmi = weight / (height_in_meters ** 2)
    return round(bmi, 2)

# Function to correct OCR mistakes
nutritional_terms = [
    "calories", "fat", "trans fat", "saturated fat", "cholesterol",
    "sodium", "carbohydrates", "sugar", "protein", "fiber", "vitamin", "iron"
]

def correct_ocr_mistakes(text):
    corrected_text = []
    for word in text.split():
        closest_match = difflib.get_close_matches(word.lower(), nutritional_terms, n=1, cutoff=0.7)
        corrected_text.append(closest_match[0] if closest_match else word)
    return ' '.join(corrected_text)

# Function to fetch user details
def fetch_user_details(email):
    return customer_collection.find_one({"email": email})

# Function to analyze food label and user profile
def prepare_data_for_rag(ocr_text, user_profile):
    documents = [
        Document(text=f"OCR corrected text from food label: {ocr_text}"),
        Document(text=f"User Profile: {user_profile}")
    ]
    return documents

def analyze_with_llama_index(ocr_text, user_profile):
    documents = prepare_data_for_rag(ocr_text, user_profile)
    index = VectorStoreIndex.from_documents(documents)

    query = query = """
You are tasked with analyzing the contents of a food label and evaluating its healthiness for a specific user.

1. Health Rating:
   - Give Rating in large size text
   - Based on the corrected food label and the user's profile, assign a health rating on a scale from 1 to 10 (where 10 is the healthiest).
   - Consider the user's dietary preferences, health goals, allergies, and activity level in your rating.
   - *If the food contains any ingredients to which the user is allergic (e.g., peanuts for a nut allergy), assign a health rating of 0/10 and include a clear warning and also before doing this be double sure that the food has a substance to which the user is allergic *.
   - If the user should avoid the food altogether, assign a rating from 1 to 4.
   - If the user should consume the food in moderation, assign a rating from 5 to 7.
   - If the user can consume the food frequently, assign a rating from 8 to 10.

2. Health Analysis:
   - Detailed Breakdown: Present a statistical breakdown of the food's nutritional content (e.g., "The food contains 2% saturated fat, 12g sugar, and 10g protein"). Ensure all terms and values are correctly spelled and reflect the accurate content of the food item.
   - Personalized Evaluation: Explain why the food item is either good or bad for the user based on their specific health profile. Double check if there actually is an item in food to which user is allergic to.  Identify any ingredients or nutritional aspects that align well or poorly with the user's dietary needs (e.g., "This food is high in sugar, which may not align with your goal of maintaining stable blood sugar levels"). **If the food contains an allergen, make sure to emphasize that.ze the risk for the user.
   - Advice: Provide guidance on whether the user should consume this food frequently, in moderation, or avoid it altogether, considering their health goals, dietary restrictions, and any allergens. **If the food contains an allergen, recommend avoiding it entirely and issue a warning in the conclusion.

Ensure that the output is free from spelling mistakes and important points or warnings are clearly communicated with bold keywords and underline  relevant details.
"""

    query_engine = index.as_query_engine()
    response = query_engine.query(query)

    return response.response

# Function for food label analysis
def analyze_food_label(image_path, email):
    result = reader.readtext(image_path)
    ocr_text = ' '.join([res[1] for res in result])
    corrected_text = correct_ocr_mistakes(ocr_text)

    user = fetch_user_details(email)
    if user:
        user_profile = {
            "BMI": user.get("bmi", "Not provided"),
            "Allergies": ', '.join(user.get("allergies", [])),
            "Health Conditions": user.get("health_conditions", "None"),
            "Dietary Preferences": user.get("dietary_preferences", "None"),
            "Activity Level": user.get("activity_level", "Moderate"),
            "Health Goals": user.get("health_goals", "General well-being")
        }

        llama_output = analyze_with_llama_index(corrected_text, user_profile)
        return llama_output
    else:
        return None

def update_user_profile(email, updated_data):
    customer_collection.update_one({"email": email}, {"$set": updated_data})

# Function to translate text using the translate library
def translate_text(text, target_lang):
    translator = Translator(to_lang=target_lang)
    max_length = 500
    translated_text = ""

    try:
        # Split the text into chunks of max_length characters
        chunks = [text[i:i+max_length] for i in range(0, len(text), max_length)]

        # Translate each chunk separately
        for chunk in chunks:
            translation = translator.translate(chunk)
            translated_text += translation

        return translated_text
    except Exception as e:
        return f"Translation error: {str(e)}"

def product_exists(product_name, brand_name):
    existing_product = product_collection.find_one({
        "Product Name": product_name,
        "Brand Name": brand_name
    })
    return existing_product is not None

# Function to update product database
def update_product_database(ocr_text, product_type=None, consumption_frequency=None):
    documents = [Document(text=f"OCR text from food label: {ocr_text}")]
    index = VectorStoreIndex.from_documents(documents)
    query_engine = index.as_query_engine()

    query = """
    You are tasked with correcting and structuring the OCR text from a food label. Please:
    1. Correct any spelling mistakes or grammatical errors in the OCR text.
    2. Extract and structure the following information:
       - Product Name
       - Brand Name (look for company names following by manufactured by or owned by or prduced by)
       - Weight in Grams/ML
       - Nutritional information: Include the serving size (e.g., "per 100g", "per 200ml") as specified on the label. If multiple serving sizes are given, use the one that provides the most comprehensive nutritional breakdown.
       - Ingredients
       - Product Category
       - Proprietary Claims: Include any claims such as "sugar-free", "low-fat", etc. If no such claims are present, leave this field empty.
    3. Present the information as a Python dictionary. The 'Nutritional information' should be a nested dictionary with the serving size as the key and the nutritional details as the value. Do not include any additional text, markdown formatting, or code blocks. Just return the dictionary.

    Example format:
    {
        "Product Name": "Example Cereal",
        "Brand Name": "HealthyBrands",
        "Weight": "500g",
        "Nutritional information": {
            "per 100g": {
                "Energy": "370kcal",
                "Protein": "8g",
                "Carbohydrates": "80g",
                "Fat": "2g"
            }
        },
        "Ingredients": "Whole grain wheat, sugar, salt",
        "Product Category": "Breakfast Cereal",
        "Proprietary Claims": "High in fiber, Low in fat"
    }

    If certain information is not available in the OCR text, use "Not specified" as the value for that key.
    """

    response = query_engine.query(query)
    
    # Extract the dictionary from the response
    dict_match = re.search(r'\{.*\}', response.response, re.DOTALL)
    if dict_match:
        try:
            product_info = ast.literal_eval(dict_match.group())
        except:
            st.error("Failed to parse the AI response. Please try again.")
            return None
    else:
        st.error("Could not extract product information from the AI response. Please try again.")
        return None

    if product_type and consumption_frequency:
        product_info['product_type'] = product_type
        product_info['consumption_frequency'] = consumption_frequency

    return product_info

# Custom CSS
def local_css(file_name):
    with open(file_name, "r") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def add_video_background():
    st.markdown("""
<style>
body {
  background-color: transparent !important;
}
.reportview-container {
  background-color: transparent !important;
}
.block-container {
  background-color: transparent !important;
}

#myVideo {
  position: fixed;
  right: 0;
  bottom: 0;
  min-width: 100%; 
  min-height: 100%;
  z-index: -1;
}

.content {
  position: fixed;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  color: #000000;
  width: 100%;
  padding: 20px;
}
</style>    
<video autoplay muted loop id="myVideo">
  <source src="https://www.spinat.fr/wp-content/uploads/2020/11/green-color-powder-explosion-on-black-isolated-bac-A5B68UY.webmhd.mp4" type="video/mp4">
  Your browser does not support HTML5 video.
</video>
""", unsafe_allow_html=True)
    

# Navigation bar
def navigation():
    selected = option_menu(
        menu_title=None,
        options=["Home", "About", "Login", "Register"],
        icons=["house", "info-circle", "box-arrow-in-right", "person-plus"],
        menu_icon="cast",
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#013220", "font-size": "25px"}, 
            "nav-link": {"font-size": "16px", "text-align": "centre", "margin":"0px", "--hover-color": "#378B29"},
            "nav-link-selected": {"background-color": "#4CAF50", "border": "2px solid black", "color": "black"},
            
        }
    )
    return selected

# Home page
def home():
    st.markdown('<div class="home-container"><h1 class="animated-text">LabelWise: An AI Powered Food Label Analyzer</h1></div>', unsafe_allow_html=True)
    st.markdown('<div class="home-container subtext" style="font-size: 1.5rem;">Empowering Healthy Choices, One Label at a Time!</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Get Started", key="get_started"):
            st.session_state.page = "Register"
            st.rerun()
    with col2:
        if st.button("Learn More", key="learn_more"):
            st.session_state.page = "About"
            st.rerun()

# About page
def about():
    st.markdown('<h1 style="font-size: 3,5rem;">About LabelWise</h1>', unsafe_allow_html=True)
    st.write("""
    LabelWise is a food label analysis tool that empowers users to make informed health decisions. It focuses on the following key functionalities:

1. Food Label Scanning: Uses Optical Character Recognition (OCR) to scan and extract information from food labels quickly.
2. Nutritional Information: Provides detailed nutritional breakdowns, including calories, fats, carbohydrates, and protein content.
3. Health Evaluation: Assesses the healthiness of food items based on user profiles and dietary preferences.
4. Error Correction: Automatically corrects OCR errors to ensure accurate information.
5. Personalized Recommendations: Suggests healthier alternatives tailored to individual dietary needs and goals.
6. User-Friendly Design: Features an intuitive interface for easy navigation and quick access to information.

LabelWise is dedicated to helping users make healthier food choices by providing accurate, actionable insights directly from food labels.
Start your journey to a healthier you today!
    """)

# Login page
def login():
    st.markdown('<h2 style="font-size: 2.5rem;">User Login</h2>', unsafe_allow_html=True)
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login"):
        user = fetch_user_details(email)
        if user and check_password(user['password'], password):
            st.session_state.logged_in = True
            st.session_state.user_email = email
            st.success(f"Welcome back, {user['name']}!")
            st.rerun()
        else:
            st.error("Invalid email or password!")

# Register page
def register():
    st.markdown('<h2 style="font-size: 2.5rem;">User Registration</h2>', unsafe_allow_html=True)
    st.info("Password must be at least 8 characters long and contain at least one uppercase letter, one digit, and one special character.")
    
    
    with st.form("registration_form"):
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
            # Check if email is already registered
            existing_user = customer_collection.find_one({"email": email})
            if existing_user:
                st.error("This email is already registered. Please use a different email.")
                return

            # Validate password strength
            if password != confirm_password:
                st.error("Passwords do not match!")
            elif not validate_password_strength(password):
                st.error("Password must be at least 8 characters long, contain one uppercase letter, one special character, and one digit.")
            else:
                bmi = calculate_bmi(weight, height)
                user_data = {
                    "name": name,
                    "email": email,
                    "password": hash_password(password),
                    "age": age,
                    "height": height,
                    "weight": weight,
                    "bmi": bmi,
                    "allergies": allergies,
                    "health_conditions": health_conditions,
                    "activity_level": activity_level,
                    "dietary_preferences": dietary_preferences,
                    "health_goals": health_goals
                }
                customer_collection.insert_one(user_data)
                st.success(f"Registration successful! Your BMI is {bmi}. Please log in.")
        
def validate_password_strength(password):
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True
def is_valid_password(password):
    return (len(password) >= 8 and
            re.search(r"[A-Z]", password) and
            re.search(r"\d", password) and
            re.search(r"[!@#$%^&*(),.?\":{}|<>]", password))
def check_email_exists(email):
    existing_user = customer_collection.find_one({"email": email})
    st.write(f"Checking email: {email}")
    st.write(f"User exists: {existing_user is not None}")
    return existing_user is not None
def main():
    st.set_page_config(layout="wide", page_icon="🥑")
    add_video_background()
    local_css("style.css")
    

    # Initialize session state variables
    if "page" not in st.session_state:
        st.session_state.page = "Home"
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_email" not in st.session_state:
        st.session_state.user_email = None
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "new_product_info" not in st.session_state:
        st.session_state.new_product_info = None

    selected = navigation()

    if not st.session_state.logged_in:
        if st.session_state.page == "Register":
            register()
            st.session_state.page = "Home"  # Reset after displaying
        elif st.session_state.page == "About":
            about()
            st.session_state.page = "Home"
        if selected == "Home":
            home()
        elif selected == "About":
            about()
        elif selected == "Login":
            login()
        elif selected == "Register":
            register()
    else:
        if selected == "Home":
            home()
        elif selected == "About":
            about()
        else:
            st.success(f"Welcome back, {st.session_state.user_email}!")
            
            # Profile Update Section
            st.subheader("Update Your Profile")
            update_profile = st.checkbox("Edit Profile")

            if update_profile:
                user = fetch_user_details(st.session_state.user_email)
                with st.form("profile_update_form"):
                    name = st.text_input("Name", value=user.get('name', ''))
                    age = st.number_input("Age", value=user.get('age', 0), min_value=1, max_value=120)
                    height = st.number_input("Height (in cm)", value=user.get('height', 0), min_value=50, max_value=250)
                    weight = st.number_input("Weight (in kg)", value=user.get('weight', 0), min_value=10, max_value=300)
                    allergies = st.text_input("Allergies", value=user.get('allergies', ''))
                    health_conditions = st.text_input("Health Conditions", value=user.get('health_conditions', ''))
                    activity_level = st.selectbox("Activity Level", ["Low", "Moderate", "High"], index=["Low", "Moderate", "High"].index(user.get('activity_level', 'Moderate')))
                    dietary_preferences = st.multiselect("Dietary Preferences", ["Vegetarian", "Vegan", "Gluten-Free", "Keto", "Paleo", "No preference"], default=user.get('dietary_preferences', []))
                    health_goals = st.selectbox("Health Goals", ["Lose weight", "Gain muscle", "Maintain weight", "Improve stamina", "General well-being"], index=["Lose weight", "Gain muscle", "Maintain weight", "Improve stamina", "General well-being"].index(user.get('health_goals', 'General well-being')))

                    update_submitted = st.form_submit_button("Update Profile")

                    if update_submitted:
                        bmi = calculate_bmi(weight, height)
                        updated_data = {
                            "name": name,
                            "age": age,
                            "height": height,
                            "weight": weight,
                            "bmi": bmi,
                            "allergies": allergies,
                            "health_conditions": health_conditions,
                            "activity_level": activity_level,
                            "dietary_preferences": dietary_preferences,
                            "health_goals": health_goals
                        }
                        update_user_profile(st.session_state.user_email, updated_data)
                        st.success(f"Profile updated successfully! Your new BMI is {bmi}.")
                        st.rerun()

            # Food Label Analysis Section
            st.subheader("Upload Food Label for Analysis")

            product_name_input = st.text_input("Product Name").lower()
            uploaded_file = st.file_uploader("Upload Food Label Image", type=["jpg", "jpeg", "png"])

            if uploaded_file and product_name_input:
                image_path = os.path.join("temp", uploaded_file.name)
                os.makedirs("temp", exist_ok=True)
                with open(image_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.success(f"Image '{uploaded_file.name}' uploaded successfully!")

                if st.button("Analyze Food Label"):
                    with st.spinner("Analyzing food label..."):
                        result = reader.readtext(image_path)
                        ocr_text = ' '.join([res[1] for res in result])

                        analysis_result = analyze_food_label(image_path, st.session_state.user_email)
                        if analysis_result:
                            st.session_state.analysis_result = analysis_result
                            st.write(analysis_result)

                            product_info = update_product_database(ocr_text)
                            if product_info:
                                product_info["Product Name"] = product_name_input
                                brand_name = product_info.get("Brand Name", "Not specified")

                                if not product_exists(product_name_input, brand_name):
                                    st.session_state.new_product_info = product_info
                                    st.rerun()
                                else:
                                    st.info("This product is already in our database.")
                            else:
                                st.error("Failed to extract product information. Please try again.")
                        else:
                            st.error("Error analyzing food label. Please try again.")

            # Handle new product information
            if st.session_state.new_product_info:
                st.subheader("Food Label Analysis")
                st.write(st.session_state.analysis_result)

                st.info("This product is not in our database. Please provide additional information:")
                with st.form(key='product_info_form'):
                    product_type = st.selectbox("Product Type", ["Nutritional", "Regular", "Recreational"])
                    consumption_frequency = st.selectbox("Consumption Frequency", ["Daily", "Weekly", "Monthly"])
                    submit_button = st.form_submit_button(label='Add to Database')
                
                if submit_button:
                    st.session_state.new_product_info['product_type'] = product_type
                    st.session_state.new_product_info['consumption_frequency'] = consumption_frequency
                    product_collection.insert_one(st.session_state.new_product_info)
                    st.success("Thank you for contributing! Product information successfully added to the database.")
                    st.session_state.new_product_info = None
                    st.rerun()

            # Translation Section
            if st.session_state.analysis_result:
                st.subheader("Translate Analysis")
                languages = {
                    "Hindi": "hi", "Bengali": "bn", "Telugu": "te", "Marathi": "mr", "Tamil": "ta",
                    "Urdu": "ur", "Gujarati": "gu", "Kannada": "kn", "Odia": "or", "Malayalam": "ml",
                    "Spanish": "es", "French": "fr", "German": "de", "Chinese": "zh", "Japanese": "ja"
                }
                target_lang = st.selectbox("Select language for translation:", list(languages.keys()))

                if st.button("Translate"):
                    with st.spinner("Translating..."):
                        translated_result = translate_text(st.session_state.analysis_result, languages[target_lang])
                        if translated_result.startswith("Translation error"):
                            st.error(translated_result)
                        else:
                            st.subheader(f"Translated Analysis ({target_lang}):")
                            st.write(translated_result)

        # Logout button
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.user_email = None
            st.session_state.analysis_result = None
            st.session_state.new_product_info = None
            st.rerun()


if __name__ == "__main__":
    main()
favicon_html = """
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🥑</text></svg>">
"""
html(favicon_html)
