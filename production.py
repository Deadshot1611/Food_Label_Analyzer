import streamlit as st
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
import ast
import json

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

1. **Health Rating**:
   - Based on the corrected food label and the user's profile, assign a health rating on a scale from **1 to 10** (where **10** is the healthiest).
   - Consider the user's dietary preferences, health goals, allergies, and activity level in your rating.
   - **If the food contains any ingredients to which the user is allergic (e.g., peanuts for a nut allergy), assign a health rating of 0/10 and include a clear warning and also before doing this be double sure that the food has a substance to which the user is allergic **.
   - If the user should avoid the food altogether, assign a rating from **1 to 4**.
   - If the user should consume the food in moderation, assign a rating from **5 to 7**.
   - If the user can consume the food frequently, assign a rating from **8 to 10**.

2. **Health Analysis**:
   - **Detailed Breakdown**: Present a statistical breakdown of the food's nutritional content (e.g., "The food contains 2% saturated fat, 12g sugar, and 10g protein"). Ensure all terms and values are correctly spelled and reflect the accurate content of the food item.
   - **Personalized Evaluation**: Explain why the food item is either good or bad for the user based on their specific health profile. Identify any ingredients or nutritional aspects that align well or poorly with the user's dietary needs (e.g., "This food is high in sugar, which may not align with your goal of maintaining stable blood sugar levels"). **If the food contains an allergen, make sure to emphasize the risk for the user**.
   - **Advice**: Provide guidance on whether the user should consume this food frequently, in moderation, or avoid it altogether, considering their health goals, dietary restrictions, and any allergens. **If the food contains an allergen, recommend avoiding it entirely and issue a warning in the conclusion**.

Ensure that the output is free from spelling mistakes and important points or warnings are clearly communicated with **bold keywords** to highlight relevant details.
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

# Function to translate text using Google Translate API
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
       - Brand Name
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
# Streamlit UI
# Streamlit UI
# Streamlit UI
st.title("Health & Nutrition Analyzer")

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "new_product_info" not in st.session_state:
    st.session_state.new_product_info = None

# Main application logic
if not st.session_state.logged_in:
    # Login and Registration Section
    st.subheader("Login or Register")

    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab1:
        st.subheader("User Login")
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

    with tab2:
        st.subheader("User Registration")
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
                if password != confirm_password:
                    st.error("Passwords do not match!")
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

    # Database Contribution Section (before login)
    st.subheader("Contribute to Food Label Database")
    contribute_toggle = st.checkbox("Help us? Contribute to our database")

    if contribute_toggle:
        with st.form("contribution_form"):
            uploaded_file = st.file_uploader("Upload Food Label Image", type=["jpg", "jpeg", "png"], key="contribute_upload")
            product_type = st.selectbox("Product Type", ["Nutritional", "Regular", "Recreational"])
            consumption_frequency = st.selectbox("Consumption Frequency", ["Daily", "Weekly", "Monthly"])
            submit_button = st.form_submit_button("Process and Submit Label")

        if submit_button and uploaded_file:
            with st.spinner("Processing and submitting food label..."):
                image_path = os.path.join("temp", uploaded_file.name)
                os.makedirs("temp", exist_ok=True)
                with open(image_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # Perform OCR
                result = reader.readtext(image_path)
                ocr_text = ' '.join([res[1] for res in result])

                # Update database
                product_info = update_product_database(ocr_text, product_type, consumption_frequency)
                
                if product_info:
                    product_name = product_info.get("Product Name", "Not specified")
                    brand_name = product_info.get("Brand Name", "Not specified")
                    
                    if not product_exists(product_name, brand_name):
                        product_collection.insert_one(product_info)
                        st.success("Thank you for contributing to our database!")
                    else:
                        st.info("This product is already in our database. Thank you for your contribution!")
                else:
                    st.error("Error processing the food label. Please try again.")

else:
    st.success(f"Welcome back, {st.session_state.user_email}!")

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user_email = None
        st.session_state.analysis_result = None
        st.session_state.new_product_info = None
        st.rerun()

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
    uploaded_file = st.file_uploader("Upload Food Label Image", type=["jpg", "jpeg", "png"])

    if uploaded_file:
        image_path = os.path.join("temp", uploaded_file.name)
        os.makedirs("temp", exist_ok=True)
        with open(image_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.image(image_path, caption="Uploaded Food Label", use_column_width=True)

        if st.button("Analyze Food Label"):
            with st.spinner("Analyzing food label..."):
                result = reader.readtext(image_path)
                ocr_text = ' '.join([res[1] for res in result])

                # Analyze the full label
                analysis_result = analyze_food_label(image_path, st.session_state.user_email)
                if analysis_result:
                    st.session_state.analysis_result = analysis_result
                    st.write(analysis_result)

                    # Extract product information
                    product_info = update_product_database(ocr_text)
                    if product_info:
                        product_name = product_info.get("Product Name", "Not specified")
                        brand_name = product_info.get("Brand Name", "Not specified")

                        if not product_exists(product_name, brand_name):
                            st.session_state.new_product_info = product_info
                            st.rerun()
                        else:
                            st.info("This product is already in our database.")
                    else:
                        st.error("Failed to extract product information. Please try again.")
                else:
                    st.error("Error analyzing food label. Please try again.")

    # Display analysis result (if available)
    # if st.session_state.analysis_result:
    #     st.subheader("Food Label Analysis")
    #     st.write(st.session_state.analysis_result)

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