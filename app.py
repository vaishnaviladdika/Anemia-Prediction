from flask import Flask, request, jsonify
import joblib
import numpy as np
import mysql.connector
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import Error
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

# Load model and scaler
try:
    loaded_rf = joblib.load('./XGBoost.joblib')
    loaded_scaler = joblib.load('./scaler.joblib')
except Exception as e:
    print(f"Error loading model or scaler: {e}")
    loaded_rf = None
    loaded_scaler = None

# MySQL connection function with error handling
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="M@ni0712",
            database="Anemia_db"
        )
        print("Database connection successful")
        return connection
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")
        return None

# Classify anemia based on hemoglobin and gender
def classify_anemia(hemoglobin, gender):
    if gender.lower() == 'male':
        if hemoglobin < 8:
            return "Severe Anemia"
        elif hemoglobin < 11:
            return "Moderate Anemia"
        elif hemoglobin < 13:
            return "Mild Anemia"
        else:
            return "Normal"
    else:
        if hemoglobin < 8:
            return "Severe Anemia"
        elif hemoglobin < 11:
            return "Moderate Anemia"
        elif hemoglobin < 12:
            return "Mild Anemia"
        else:
            return "Normal"

# API: Predict Hemoglobin
@app.route('/predict', methods=['POST'])
def predict():
    if not loaded_rf or not loaded_scaler:
        return jsonify({'error': 'Model or scaler not loaded properly'}), 500

    try:
        data = request.json
        # Ensure required fields are present
        required_fields = ['age', 'gender', 'platelet_count', 'wbc', 'rbc', 'mcv', 'mch', 'mchc']
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Parse and process input data
        age = float(data['age'])
        gender = data['gender'].lower()
        platelet_count = float(data['platelet_count'])
        wbc = float(data['wbc'])
        rbc = float(data['rbc'])
        mcv = float(data['mcv'])
        mch = float(data['mch'])
        mchc = float(data['mchc'])

        gender_encoded = 1 if gender == 'male' else 0
        input_data = np.array([[age, gender_encoded, platelet_count, wbc, rbc, mcv, mch, mchc]])
        input_scaled = loaded_scaler.transform(input_data)

        predicted_hemoglobin = loaded_rf.predict(input_scaled)[0]
        anemia_class = classify_anemia(predicted_hemoglobin, gender)

        # Calculate confidence (for simplicity, using standard deviation of the model predictions)
        prediction_variance = np.std(loaded_rf.predict(input_scaled))  # Using model's prediction variance for confidence
        confidence = max(0, min(1, 1 - prediction_variance))  # Normalize confidence between 0 and 1

        return jsonify({
            'hemoglobin': predicted_hemoglobin,
            'anemia_class': anemia_class,
        })
    except Exception as e:
        return jsonify({'error': f"Error during prediction: {str(e)}"}), 400

@app.route('/save_prediction', methods=['POST'])
def save_prediction():
    try:
        data = request.json
        print(f"Received data for saving prediction: {data}")  # Debugging line

        user_id = data['user_id']
        hemoglobin = float(data['hemoglobin'])
        result = data['anemia_class']

        # Check if user_id exists in the users table
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            print(f"User with ID {user_id} not found.")  # Debugging line
            return jsonify({'error': f'User with user_id {user_id} does not exist'}), 400

        # Proceed with the insert into predictions table
        query = "INSERT INTO predictions (user_id, hemoglobin_level, result) VALUES (%s, %s, %s)"
        cursor.execute(query, (user_id, hemoglobin, result))
        db.commit()

        print("Prediction data inserted successfully.")  # Debugging line
        cursor.close()
        db.close()
        return jsonify({'message': 'Prediction saved successfully!'})
    except mysql.connector.Error as db_err:
        print(f"MySQL Error: {db_err}")  # Debugging line
        return jsonify({'error': f"MySQL Error: {str(db_err)}"}), 500
    except Exception as e:
        print(f"Error: {e}")  # Debugging line
        return jsonify({'error': f"Error: {str(e)}"}), 400


@app.route('/history/<userId>', methods=['GET'])
def get_history(userId):
    try:
        # Validate userId
        if not userId.isdigit():
            return jsonify({"error": "Invalid userId"}), 400
        db = get_db_connection()
        cursor = db.cursor()
        
        # Fetch history from the predictions table instead of the history table
        cursor.execute("SELECT * FROM predictions WHERE user_id = %s", (userId,))
        results = cursor.fetchall()
        
        if not results:
            return jsonify({"error": "No history found"}), 404
        
        # Return history
        history = [{"id": row[0], "hemoglobin": row[2], "anemia_class": row[3], "test_date": datetime.strftime(row[4], "%Y-%m-%d")} for row in results]
        return jsonify(history), 200

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Server error"}), 500

# Signup and Login endpoints with password hashing
@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data['email']
        password = data['password']

        # Establish database connection
        db = get_db_connection()
        if db is None:
            return jsonify({'error': 'Database connection failed'}), 500
        
        # Query to check if the email exists
        cursor = db.cursor()
        cursor.execute("SELECT user_id, password FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user is None:
            return jsonify({'error': 'User not found'}), 404
        
        stored_user_id, stored_password = user

        # Check if the password matches
        if check_password_hash(stored_password, password):
            return jsonify({'user_id': stored_user_id}), 200
        else:
            return jsonify({'error': 'Invalid credentials'}), 401
        
    except Exception as e:
        return jsonify({'error': f"Error during login: {str(e)}"}), 400

@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        email = data['email']
        password = data['password']

        # Hash password before saving
        hashed_password = generate_password_hash(password)

        # Establish database connection
        db = get_db_connection()
        if db is None:
            return jsonify({'error': 'Database connection failed'}), 500
        
        # Insert user into the users table
        cursor = db.cursor()
        cursor.execute("INSERT INTO users (email, password) VALUES (%s, %s)", (email, hashed_password))
        db.commit()

        # Fetch the newly inserted user_id
        cursor.execute("SELECT LAST_INSERT_ID()")
        user_id = cursor.fetchone()[0]

        cursor.close()
        db.close()

        # Return the user_id as the response
        return jsonify({'user_id': user_id}), 201
    except Exception as e:
        return jsonify({'error': f"Error during signup: {str(e)}"}), 400

if __name__ == '__main__':
    app.run(debug=True)
