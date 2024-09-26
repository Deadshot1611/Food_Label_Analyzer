import streamlit as st
import easyocr
import cv2
import numpy as np
from PIL import Image

# Title of the Streamlit app
st.title('OCR using EasyOCR')

# Upload an image file
uploaded_file = st.file_uploader("Upload an image with text", type=['jpg', 'jpeg', 'png'])

if uploaded_file is not None:
    # Load the uploaded image using PIL
    img = Image.open(uploaded_file)
    
    # Convert PIL image to a format suitable for OpenCV (numpy array)
    img_array = np.array(img)
    
    # Display the uploaded image in the Streamlit app
    st.image(img, caption='Uploaded Image', use_column_width=True)
    
    # Create an EasyOCR reader object (with English as the language)
    reader = easyocr.Reader(['en'])
    
    # Perform OCR on the image
    with st.spinner('Processing...'):
        result = reader.readtext(img_array)
    
    # Show the results
    st.subheader('Extracted Text:')
    
    # If text is found, display it
    if len(result) > 0:
        for (bbox, text, prob) in result:
            st.write(f'Text: {text}, Confidence: {prob:.2f}')
    else:
        st.write("No text found.")

