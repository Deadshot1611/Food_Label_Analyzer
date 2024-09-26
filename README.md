# LabelWise: An AI-powered Food Label Analyzer

[Visit the live app here!](https://deadshot2003-food-label-analyzer.hf.space)

**LabelWise** is an intelligent tool that helps users make informed food choices by analyzing product labels based on their individual health profiles. By using cutting-edge AI, the app evaluates the nutritional content of products and provides users with a personalized health rating, helping them align their food consumption with their health goals.

## Features

- **User Registration and Profile Setup**: 
  - Register by providing your name, email, password, age, height, weight (BMI auto-calculated), health conditions, allergies, activity level, food preferences, and health goals.
  - Edit your profile anytime to ensure recommendations are always relevant.

- **Login and Personal Dashboard**: 
  - Secure login with email and password. Access your personalized dashboard with options to edit your profile, analyze products, and more.

- **AI-Powered Label Analysis**: 
  - Upload the back label of any product, and our AI model analyzes it against your health profile.
  - Get instant feedback including a health rating based on nutritional data and your individual preferences.

- **Database Recognition**: 
  - If the product is already in our database, get instant access to its details.
  - If it's new, answer two simple questions: product type and consumption frequency.

- **Multilingual Support**: 
  - Translate AI analysis into any world language and most Indian regional languages for easy comprehension.

- **Health Ratings**: 
  - Receive a personalized health rating for each product based on your profile and its nutritional content.

- **Logout**: 
  - Easily logout and secure your information when done.

## Getting Started

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/yourusername/LabelWise.git
   cd LabelWise
2.**Install Dependencies**:

Ensure you have Python installed. Then, install the required Python packages by running:

```bash
pip install -r requirements.txt

3. **Environment Setup**:

You'll need to set up environment variables for MongoDB Atlas and any other API keys required.

1. Create a `.env` file in the root directory of your project.
2. Add your MongoDB connection string and any other secret keys in the `.env` file.

Example:

```bash
MONGODB_URI=your_mongodb_uri
SECRET_KEY=your_secret_key
4. **Running the Application**:

After setting up your environment and installing all required dependencies, you can run the LabelWise application using the following command:

```bash
streamlit run app.py
