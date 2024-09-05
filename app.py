from flask_caching import Cache
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from datetime import datetime
import os
from functools import wraps
from geopy.geocoders import Nominatim
import folium

# Configuration
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_random_secret_key'
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/oxyleap'
    CACHE_TYPE = "RedisCache"
    CACHE_REDIS_URL = "redis://localhost:6379/0"  # Default Redis URL

# Initialize Flask app, MongoDB connection, and Cache
app = Flask(__name__)
app.config.from_object(Config)
mongo = PyMongo(app)
cache = Cache(app)

# Load the india_cities.csv data
city_data = pd.read_csv('data/india_cities.csv')

# Function to find lat/lon based on city, state, country
def find_lat_lon(city, state, country):
    result = city_data[
        (city_data['city'].str.strip().str.lower() == city.strip().lower()) &
        (city_data['state'].str.strip().str.lower() == state.strip().lower()) &
        (city_data['country'].str.strip().str.lower() == country.strip().lower())
    ]
    print(f"Filtered result for city: {city}, state: {state}, country: {country} - Found rows: {len(result)}")
    
    if not result.empty:
        return result.iloc[0]['latitude'], result.iloc[0]['longitude']
    return None, None

# Data Import Function
def import_hospital_dataset(csv_path):
    if mongo.db.hospitals.count_documents({}) == 0:  # Check if the collection is empty
        df = pd.read_csv(csv_path)
        mongo.db.hospitals.insert_many(df.to_dict('records'))
        print("Hospital data imported successfully.")
    else:
        print("Hospital data already exists in the database.")

# Models
def get_user_by_username(username):
    return mongo.db.users.find_one({'username': username})

def create_user(email, username, password_hash):
    mongo.db.users.insert_one({
        'email': email,
        'username': username,
        'password': password_hash
    })

def get_hospitals(query=None):
    if query:
        return mongo.db.hospitals.find(query)
    return mongo.db.hospitals.find()

def get_hospitals_by_type(hospital_type):
    return mongo.db.hospitals.find({'hospital_type': hospital_type})

def get_hospitals_with_emergency_services():
    return mongo.db.hospitals.find({'emergency_services': 'Yes'})

def get_hospital_by_id(facility_id):
    return mongo.db.hospitals.find_one({'facility_id': facility_id})

def add_review(hospital_id, review, rating):
    mongo.db.reviews.insert_one({
        'hospital_id': hospital_id,
        'review': review,
        'rating': rating,
        'timestamp': datetime.now()
    })

def get_reviews():
    return mongo.db.reviews.find().sort('timestamp', -1)

def update_bed_status(hospital_id, status):
    mongo.db.hospitals.update_one(
        {'facility_id': hospital_id},
        {'$set': {'bed_status': status}}
    )

@cache.memoize(timeout=3600)  # Cache results for 1 hour
def predict_bed_availability(facility_id):
    bed_stat = mongo.db.bed_stats.find_one({"facility_id": facility_id})
    
    if not bed_stat:
        return {"status": "Unknown", "inactive_beds": "N/A"}  # Return a dictionary with default values

    # Convert the 'bed_stats' document to a DataFrame
    df = pd.DataFrame(bed_stat["data"])
    
    # Ensure the dataset contains the necessary columns
    if 'Active Beds' not in df.columns or 'Inactive Beds' not in df.columns:
        return {"status": "Unknown", "inactive_beds": "N/A"}
    
    # Calculate the average active beds
    avg_active_beds = df['Active Beds'].mean()
    
    # Use the last entry of Active Beds as a simple prediction
    next_month_prediction = df['Active Beds'].iloc[-1]
    
    # Get the most recent inactive beds count
    inactive_beds = df['Inactive Beds'].iloc[-1] if 'Inactive Beds' in df.columns else 'N/A'

    # Determine the status based on the predicted value
    if next_month_prediction > avg_active_beds:
        return {"status": "red", "inactive_beds": inactive_beds}  # Less vacant beds
    elif next_month_prediction >= (avg_active_beds * 0.8):
        return {"status": "yellow", "inactive_beds": inactive_beds}  # Medium vacant beds
    else:
        return {"status": "green", "inactive_beds": inactive_beds}  # More vacant beds


# Helper: Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('You need to be signed in to access this page.', 'warning')
            return redirect(url_for('signin'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
@login_required
def index():
    return render_template('page1.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        password_hash = generate_password_hash(password)
        create_user(email, username, password_hash)
        flash('Account created successfully! Please sign in to continue.', 'success')
        return redirect(url_for('signin'))
    return render_template('signup.html')

@app.route('/signin', methods=['GET', 'POST'])
def signin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user_by_username(username)
        if user and check_password_hash(user['password'], password):
            session['username'] = username  # Log the user in
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials!', 'danger')
    return render_template('signin.html')

@app.route('/logout')
def logout():
    session.pop('username', None)  # Log the user out
    flash('You have been logged out.', 'info')
    return redirect(url_for('signin'))

@app.route('/location', methods=['GET', 'POST'])
@login_required
def location():
    # Fetch distinct values for dropdowns
    cities = mongo.db.hospitals.distinct('city')
    states = mongo.db.hospitals.distinct('state')
    counties = mongo.db.hospitals.distinct('county')
    hospital_types = mongo.db.hospitals.distinct('hospital_type')

    hospitals = []
    if request.method == 'POST':
        city = request.form['city']
        state = request.form['state']
        county = request.form['county']
        hospital_type = request.form['hospital_type']
        query = {}
        if city:
            query['city'] = city
        if state:
            query['state'] = state
        if county:
            query['county'] = county
        if hospital_type:
            query['hospital_type'] = hospital_type
        hospitals = list(get_hospitals(query))
    
    return render_template('location.html', hospitals=hospitals, cities=cities, states=states, counties=counties, hospital_types=hospital_types)


@app.route('/confirm_location/<hospital_id>', methods=['GET', 'POST'])
@login_required
def confirm_location(hospital_id):
    city = request.args.get('city')
    state = request.args.get('state')
    hospital = get_hospital_by_id(hospital_id)
    if not hospital:
        flash("Hospital not found.", "danger")
        return redirect(url_for('health_centers'))
    
    if request.method == 'POST':
        # Get the user's input for location confirmation
        city = request.form['city']
        state = request.form['state']
        country = request.form['country']
        
        # Use the india_cities.csv data to find the latitude and longitude
        latitude, longitude = find_lat_lon(city, state, country)
        
        if latitude is not None and longitude is not None:
            # Update session with the confirmed location
            session['user_city'] = city
            session['user_state'] = state
            session['user_lat'] = latitude
            session['user_lon'] = longitude
            session['user_location_confirmed'] = True
            # Redirect to navigate page with hospital information
            return redirect(url_for('navigate', hospital_id=hospital_id))
        else:
            flash("Location could not be found in the database. Please try again.", "danger")
    
    return render_template('confirm_location.html', city=city, state=state, hospital=hospital)

@app.route('/navigate/<hospital_id>')
@login_required
def navigate(hospital_id):
    hospital = get_hospital_by_id(hospital_id)
    if not hospital:
        flash("Hospital not found.", "danger")
        return redirect(url_for('health_centers'))
    
    address = hospital['address']
    city = hospital['city']
    state = hospital['state']

    # Geocode the hospital address to get latitude and longitude
    geolocator = Nominatim(user_agent="oxyleap")
    location = geolocator.geocode(f"{address}, {city}, {state}")

    if location:
        # Create a Folium map centered on the hospital location
        hospital_map = folium.Map(location=[location.latitude, location.longitude], zoom_start=13)

        # Add a marker for the hospital
        folium.Marker([location.latitude, location.longitude], tooltip=f"{address}, {city}, {state}").add_to(hospital_map)

        # Retrieve user location from session
        user_lat = session.get('user_lat', 37.7749)
        user_lon = session.get('user_lon', -122.4194)
        folium.Marker([user_lat, user_lon], tooltip="User Location", icon=folium.Icon(color='green')).add_to(hospital_map)

        # Add a route from user location to hospital
        folium.PolyLine(locations=[[user_lat, user_lon], [location.latitude, location.longitude]], color="red").add_to(hospital_map)

        # Render the map in the template
        map_html = hospital_map._repr_html_()
    else:
        flash("Location not found.", "danger")
        return redirect(url_for('location'))

    return render_template('navigation.html', map_html=map_html)

@app.route('/health_centers', methods=['GET', 'POST'])
@login_required
def health_centers():
    filter_type = request.args.get('filter', 'semi-urgent').lower()  # Default to semi-urgent
    
    hospitals = list(get_hospitals())

    # Predict bed availability status for each hospital
    for hospital in hospitals:
        facility_id = hospital['facility_id']
        prediction = predict_bed_availability(facility_id)
        hospital['bed_status'] = prediction.get('status', 'Unknown')
        hospital['inactive_beds'] = prediction.get('inactive_beds', 'N/A')

    # Apply filters based on the button clicked
    if filter_type == 'immediate':
        filtered_hospitals = [hospital for hospital in hospitals if hospital['bed_status'] == 'green' and hospital['hospital_type'] == 'Critical Access Hospitals']
    elif filter_type == 'emergency':
        filtered_hospitals = [hospital for hospital in hospitals if hospital['bed_status'] in ['green', 'yellow'] and hospital['hospital_type'] == 'Critical Access Hospitals']
    elif filter_type == 'urgent' or filter_type == 'semi-urgent':
        filtered_hospitals = [hospital for hospital in hospitals if hospital['bed_status'] in ['green', 'yellow', 'red']]

    return render_template('health_centers.html', hospitals=filtered_hospitals, filter_type=filter_type)


@app.route('/hospital_info')
def hospital_about():
    hospital_name = request.args.get('hospital_name')
    # Replace spaces with hyphens and convert to lowercase to match the ID format
    formatted_name = hospital_name.replace(' ', '-').replace("'", "").lower()

    return render_template('hospital_info.html', hospital_name=formatted_name)



@app.route('/emergency')
@login_required
def emergency():
    hospitals = get_hospitals_with_emergency_services()
    return render_template('emergency.html', hospitals=hospitals)

@app.route('/acute_care')
@login_required
def acute_care():
    hospitals = get_hospitals_by_type('Acute Care Hospitals')
    return render_template('acute_care.html', hospitals=hospitals)

@app.route('/critical_care')
@login_required
def critical_care():
    hospitals = get_hospitals_by_type('Critical Access Hospitals')
    return render_template('critical_care.html', hospitals=hospitals)

@app.route('/childrens')
@login_required
def childrens():
    hospitals = get_hospitals_by_type('Children\'s')
    return render_template('childrens.html', hospitals=hospitals)

@app.route('/psychiatric')
@login_required
def psychiatric():
    hospitals = get_hospitals_by_type('Psychiatric')
    return render_template('psychiatric.html', hospitals=hospitals)

@app.route('/review/<hospital_id>', methods=['GET', 'POST'])
@login_required
def review(hospital_id):
    hospital = get_hospital_by_id(hospital_id)
    if request.method == 'POST':
        review_text = request.form['review']
        rating = request.form['rating']
        add_review(hospital_id, review_text, rating)
        return redirect(url_for('records'))
    return render_template('review.html', hospital=hospital)

@app.route('/records')
@login_required
def records():
    reviews = get_reviews()
    return render_template('records.html', reviews=reviews)

if __name__ == '__main__':
    import_hospital_dataset('data/hospital_dataset.csv')  # Import data from the CSV file
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    pywsgi.WSGIServer(('', 8080), app, handler_class=WebSocketHandler).serve_forever()














# from flask_caching import Cache
# from flask import Flask, render_template, request, redirect, url_for, flash, session
# from flask_pymongo import PyMongo
# from werkzeug.security import generate_password_hash, check_password_hash
# import pandas as pd
# from sklearn.model_selection import train_test_split
# from sklearn.ensemble import RandomForestClassifier
# from sklearn.metrics import accuracy_score
# from datetime import datetime
# import os
# from functools import wraps
# from geopy.geocoders import Nominatim
# import folium

# # Configuration
# class Config:
#     SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_random_secret_key'
#     MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/oxyleap'
#     CACHE_TYPE = "RedisCache"
#     CACHE_REDIS_URL = "redis://localhost:6379/0"  # Default Redis URL

# # Initialize Flask app, MongoDB connection, and Cache
# app = Flask(__name__)
# app.config.from_object(Config)
# mongo = PyMongo(app)
# cache = Cache(app)

# # Load the india_cities.csv data
# city_data = pd.read_csv('data/india_cities.csv')

# # Function to find lat/lon based on city, state, country
# def find_lat_lon(city, state, country):
#     result = city_data[
#         (city_data['city'].str.strip().str.lower() == city.strip().lower()) &
#         (city_data['state'].str.strip().str.lower() == state.strip().lower()) &
#         (city_data['country'].str.strip().str.lower() == country.strip().lower())
#     ]
#     print(f"Filtered result for city: {city}, state: {state}, country: {country} - Found rows: {len(result)}")
    
#     if not result.empty:
#         return result.iloc[0]['latitude'], result.iloc[0]['longitude']
#     return None, None

# # Data Import Function
# def import_hospital_dataset(csv_path):
#     if mongo.db.hospitals.count_documents({}) == 0:  # Check if the collection is empty
#         df = pd.read_csv(csv_path)
#         mongo.db.hospitals.insert_many(df.to_dict('records'))
#         print("Hospital data imported successfully.")
#     else:
#         print("Hospital data already exists in the database.")

# # Models
# def get_user_by_username(username):
#     return mongo.db.users.find_one({'username': username})

# def create_user(email, username, password_hash):
#     mongo.db.users.insert_one({
#         'email': email,
#         'username': username,
#         'password': password_hash
#     })

# def get_hospitals(query=None):
#     if query:
#         return mongo.db.hospitals.find(query)
#     return mongo.db.hospitals.find()

# def get_hospitals_by_type(hospital_type):
#     return mongo.db.hospitals.find({'hospital_type': hospital_type})

# def get_hospitals_with_emergency_services():
#     return mongo.db.hospitals.find({'emergency_services': 'Yes'})

# def get_hospital_by_id(facility_id):
#     return mongo.db.hospitals.find_one({'facility_id': facility_id})

# def add_review(hospital_id, review, rating):
#     mongo.db.reviews.insert_one({
#         'hospital_id': hospital_id,
#         'review': review,
#         'rating': rating,
#         'timestamp': datetime.now()
#     })

# def get_reviews():
#     return mongo.db.reviews.find().sort('timestamp', -1)

# def update_bed_status(hospital_id, status):
#     mongo.db.hospitals.update_one(
#         {'facility_id': hospital_id},
#         {'$set': {'bed_status': status}}
#     )

# @cache.memoize(timeout=3600)  # Cache results for 1 hour
# def predict_bed_availability(facility_id):
#     bed_stat = mongo.db.bed_stats.find_one({"facility_id": facility_id})
    
#     if not bed_stat:
#         return "Unknown"  # If the facility's data doesn't exist, return an unknown status

#     # Convert the 'bed_stats' document to a DataFrame
#     df = pd.DataFrame(bed_stat["data"])
    
#     # Ensure the dataset contains the necessary columns
#     if 'Active Beds' not in df.columns or 'Inactive Beds' not in df.columns:
#         return "Unknown"
    
#     # Calculate the average active beds
#     avg_active_beds = df['Active Beds'].mean()
    
#     # Use the last entry of Active Beds as a simple prediction
#     next_month_prediction = df['Active Beds'].iloc[-1]
    
#     # Determine the status based on the predicted value
#     if next_month_prediction > avg_active_beds:
#         return "red"  # Less vacant beds
#     elif next_month_prediction >= (avg_active_beds * 0.8):
#         return "yellow"  # Medium vacant beds
#     else:
#         return "green"  # More vacant beds

# # Helper: Login Required Decorator
# def login_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'username' not in session:
#             flash('You need to be signed in to access this page.', 'warning')
#             return redirect(url_for('signin'))
#         return f(*args, **kwargs)
#     return decorated_function

# # Routes
# @app.route('/')
# @login_required
# def index():
#     return render_template('page1.html')

# @app.route('/signup', methods=['GET', 'POST'])
# def signup():
#     if request.method == 'POST':
#         email = request.form['email']
#         username = request.form['username']
#         password = request.form['password']
#         password_hash = generate_password_hash(password)
#         create_user(email, username, password_hash)
#         flash('Account created successfully! Please sign in to continue.', 'success')
#         return redirect(url_for('signin'))
#     return render_template('signup.html')

# @app.route('/signin', methods=['GET', 'POST'])
# def signin():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']
#         user = get_user_by_username(username)
#         if user and check_password_hash(user['password'], password):
#             session['username'] = username  # Log the user in
#             flash('Login successful!', 'success')
#             return redirect(url_for('index'))
#         flash('Invalid credentials!', 'danger')
#     return render_template('signin.html')

# @app.route('/logout')
# def logout():
#     session.pop('username', None)  # Log the user out
#     flash('You have been logged out.', 'info')
#     return redirect(url_for('signin'))

# @app.route('/location', methods=['GET', 'POST'])
# @login_required
# def location():
#     # Fetch distinct values for dropdowns
#     cities = mongo.db.hospitals.distinct('city')
#     states = mongo.db.hospitals.distinct('state')
#     counties = mongo.db.hospitals.distinct('county')
#     hospital_types = mongo.db.hospitals.distinct('hospital_type')

#     hospitals = []
#     if request.method == 'POST':
#         city = request.form['city']
#         state = request.form['state']
#         county = request.form['county']
#         hospital_type = request.form['hospital_type']
#         query = {}
#         if city:
#             query['city'] = city
#         if state:
#             query['state'] = state
#         if county:
#             query['county'] = county
#         if hospital_type:
#             query['hospital_type'] = hospital_type
#         hospitals = list(get_hospitals(query))
    
#     return render_template('location.html', hospitals=hospitals, cities=cities, states=states, counties=counties, hospital_types=hospital_types)


# @app.route('/confirm_location/<hospital_id>', methods=['GET', 'POST'])
# @login_required
# def confirm_location(hospital_id):
#     city = request.args.get('city')
#     state = request.args.get('state')
#     hospital = get_hospital_by_id(hospital_id)
#     if not hospital:
#         flash("Hospital not found.", "danger")
#         return redirect(url_for('health_centers'))
    
#     if request.method == 'POST':
#         # Get the user's input for location confirmation
#         city = request.form['city']
#         state = request.form['state']
#         country = request.form['country']
        
#         # Use the india_cities.csv data to find the latitude and longitude
#         latitude, longitude = find_lat_lon(city, state, country)
        
#         if latitude is not None and longitude is not None:
#             # Update session with the confirmed location
#             session['user_city'] = city
#             session['user_state'] = state
#             session['user_lat'] = latitude
#             session['user_lon'] = longitude
#             session['user_location_confirmed'] = True
#             # Redirect to navigate page with hospital information
#             return redirect(url_for('navigate', hospital_id=hospital_id))
#         else:
#             flash("Location could not be found in the database. Please try again.", "danger")
    
#     return render_template('confirm_location.html', city=city, state=state, hospital=hospital)

# @app.route('/navigate/<hospital_id>')
# @login_required
# def navigate(hospital_id):
#     hospital = get_hospital_by_id(hospital_id)
#     if not hospital:
#         flash("Hospital not found.", "danger")
#         return redirect(url_for('health_centers'))
    
#     address = hospital['address']
#     city = hospital['city']
#     state = hospital['state']

#     # Geocode the hospital address to get latitude and longitude
#     geolocator = Nominatim(user_agent="oxyleap")
#     location = geolocator.geocode(f"{address}, {city}, {state}")

#     if location:
#         # Create a Folium map centered on the hospital location
#         hospital_map = folium.Map(location=[location.latitude, location.longitude], zoom_start=13)

#         # Add a marker for the hospital
#         folium.Marker([location.latitude, location.longitude], tooltip=f"{address}, {city}, {state}").add_to(hospital_map)

#         # Retrieve user location from session
#         user_lat = session.get('user_lat', 37.7749)
#         user_lon = session.get('user_lon', -122.4194)
#         folium.Marker([user_lat, user_lon], tooltip="User Location", icon=folium.Icon(color='green')).add_to(hospital_map)

#         # Add a route from user location to hospital
#         folium.PolyLine(locations=[[user_lat, user_lon], [location.latitude, location.longitude]], color="red").add_to(hospital_map)

#         # Render the map in the template
#         map_html = hospital_map._repr_html_()
#     else:
#         flash("Location not found.", "danger")
#         return redirect(url_for('location'))

#     return render_template('navigation.html', map_html=map_html)

# @app.route('/health_centers', methods=['GET', 'POST'])
# @login_required
# def health_centers():
#     filter_type = request.args.get('filter', 'semi-urgent').lower()  # Default to semi-urgent
    
#     hospitals = list(get_hospitals())

#     # Predict bed availability status for each hospital
#     for hospital in hospitals:
#         facility_id = hospital['facility_id']
#         bed_status = predict_bed_availability(facility_id)
#         hospital['bed_status'] = bed_status

#     # Apply filters based on the button clicked
#     if filter_type == 'immediate':
#         filtered_hospitals = [hospital for hospital in hospitals if hospital['bed_status'] == 'green']
#     elif filter_type == 'emergency':
#         filtered_hospitals = [hospital for hospital in hospitals if hospital['bed_status'] in ['green', 'yellow']]
#     elif filter_type == 'urgent' or filter_type == 'semi-urgent':
#         filtered_hospitals = [hospital for hospital in hospitals if hospital['bed_status'] in ['green', 'yellow', 'red']]

#     return render_template('health_centers.html', hospitals=filtered_hospitals, filter_type=filter_type)

# @app.route('/emergency')
# @login_required
# def emergency():
#     hospitals = get_hospitals_with_emergency_services()
#     return render_template('emergency.html', hospitals=hospitals)

# @app.route('/acute_care')
# @login_required
# def acute_care():
#     hospitals = get_hospitals_by_type('Acute Care Hospitals')
#     return render_template('acute_care.html', hospitals=hospitals)

# @app.route('/critical_care')
# @login_required
# def critical_care():
#     hospitals = get_hospitals_by_type('Critical Access Hospitals')
#     return render_template('critical_care.html', hospitals=hospitals)

# @app.route('/childrens')
# @login_required
# def childrens():
#     hospitals = get_hospitals_by_type('Children\'s')
#     return render_template('childrens.html', hospitals=hospitals)

# @app.route('/psychiatric')
# @login_required
# def psychiatric():
#     hospitals = get_hospitals_by_type('Psychiatric')
#     return render_template('psychiatric.html', hospitals=hospitals)

# @app.route('/review/<hospital_id>', methods=['GET', 'POST'])
# @login_required
# def review(hospital_id):
#     hospital = get_hospital_by_id(hospital_id)
#     if request.method == 'POST':
#         review_text = request.form['review']
#         rating = request.form['rating']
#         add_review(hospital_id, review_text, rating)
#         return redirect(url_for('records'))
#     return render_template('review.html', hospital=hospital)

# @app.route('/records')
# @login_required
# def records():
#     reviews = get_reviews()
#     return render_template('records.html', reviews=reviews)

# if __name__ == '__main__':
#     import_hospital_dataset('data/hospital_dataset.csv')  # Import data from the CSV file
#     app.run(debug=True)

















# from flask import Flask, render_template, request, redirect, url_for, flash, session
# from flask_pymongo import PyMongo
# from werkzeug.security import generate_password_hash, check_password_hash
# import pandas as pd
# from sklearn.model_selection import train_test_split
# from sklearn.ensemble import RandomForestClassifier
# from datetime import datetime
# import os
# from functools import wraps
# from geopy.geocoders import Nominatim
# import folium

# # Configuration
# class Config:
#     SECRET_KEY = os.environ.get('SECRET_KEY') or 'a_random_secret_key'
#     MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb://localhost:27017/oxyleap'

# # Initialize Flask app and MongoDB connection
# app = Flask(__name__)
# app.config.from_object(Config)
# mongo = PyMongo(app)

# # Load the india_cities.csv data
# city_data = pd.read_csv('data/india_cities.csv')

# # Function to find lat/lon based on city, state, country
# def find_lat_lon(city, state, country):
#     result = city_data[
#         (city_data['city'].str.strip().str.lower() == city.strip().lower()) &
#         (city_data['state'].str.strip().str.lower() == state.strip().lower()) &
#         (city_data['country'].str.strip().str.lower() == country.strip().lower())
#     ]
#     print(f"Filtered result for city: {city}, state: {state}, country: {country} - Found rows: {len(result)}")
    
#     if not result.empty:
#         return result.iloc[0]['latitude'], result.iloc[0]['longitude']
#     return None, None


# # Data Import Function
# def import_hospital_dataset(csv_path):
#     if mongo.db.hospitals.count_documents({}) == 0:  # Check if the collection is empty
#         df = pd.read_csv(csv_path)
#         mongo.db.hospitals.insert_many(df.to_dict('records'))
#         print("Hospital data imported successfully.")
#     else:
#         print("Hospital data already exists in the database.")

# # Models
# def get_user_by_username(username):
#     return mongo.db.users.find_one({'username': username})

# def create_user(email, username, password_hash):
#     mongo.db.users.insert_one({
#         'email': email,
#         'username': username,
#         'password': password_hash
#     })

# def get_hospitals(query=None):
#     if query:
#         return mongo.db.hospitals.find(query)
#     return mongo.db.hospitals.find()

# def get_hospitals_by_type(hospital_type):
#     return mongo.db.hospitals.find({'hospital_type': hospital_type})

# def get_hospitals_with_emergency_services():
#     return mongo.db.hospitals.find({'emergency_services': 'Yes'})

# def get_hospital_by_id(facility_id):
#     return mongo.db.hospitals.find_one({'facility_id': facility_id})

# def add_review(hospital_id, review, rating):
#     mongo.db.reviews.insert_one({
#         'hospital_id': hospital_id,
#         'review': review,
#         'rating': rating,
#         'timestamp': datetime.now()
#     })

# def get_reviews():
#     return mongo.db.reviews.find().sort('timestamp', -1)

# def update_bed_status(hospital_id, status):
#     mongo.db.hospitals.update_one(
#         {'facility_id': hospital_id},
#         {'$set': {'bed_status': status}}
#     )

# # Helper: Login Required Decorator
# def login_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'username' not in session:
#             flash('You need to be signed in to access this page.', 'warning')
#             return redirect(url_for('signin'))
#         return f(*args, **kwargs)
#     return decorated_function

# # Routes
# @app.route('/')
# @login_required
# def index():
#     return render_template('page1.html')

# @app.route('/signup', methods=['GET', 'POST'])
# def signup():
#     if request.method == 'POST':
#         email = request.form['email']
#         username = request.form['username']
#         password = request.form['password']
#         password_hash = generate_password_hash(password)
#         create_user(email, username, password_hash)
#         flash('Account created successfully! Please sign in to continue.', 'success')
#         return redirect(url_for('signin'))
#     return render_template('signup.html')

# @app.route('/signin', methods=['GET', 'POST'])
# def signin():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']
#         user = get_user_by_username(username)
#         if user and check_password_hash(user['password'], password):
#             session['username'] = username  # Log the user in
#             flash('Login successful!', 'success')
#             return redirect(url_for('index'))
#         flash('Invalid credentials!', 'danger')
#     return render_template('signin.html')

# @app.route('/logout')
# def logout():
#     session.pop('username', None)  # Log the user out
#     flash('You have been logged out.', 'info')
#     return redirect(url_for('signin'))

# @app.route('/location', methods=['GET', 'POST'])
# @login_required
# def location():
#     # Fetch distinct values for dropdowns
#     cities = mongo.db.hospitals.distinct('city')
#     states = mongo.db.hospitals.distinct('state')
#     counties = mongo.db.hospitals.distinct('county')
#     hospital_types = mongo.db.hospitals.distinct('hospital_type')

#     hospitals = []
#     if request.method == 'POST':
#         city = request.form['city']
#         state = request.form['state']
#         county = request.form['county']
#         hospital_type = request.form['hospital_type']
#         query = {}
#         if city:
#             query['city'] = city
#         if state:
#             query['state'] = state
#         if county:
#             query['county'] = county
#         if hospital_type:
#             query['hospital_type'] = hospital_type
#         hospitals = get_hospitals(query)
#         # Store the hospital query in session and redirect to confirm location page
#         session['hospital_query'] = query
#         return redirect(url_for('confirm_location', city=city, state=state))
    
#     if session.get('hospital_query'):
#         hospitals = get_hospitals(session['hospital_query'])
    
#     return render_template('location.html', hospitals=hospitals, cities=cities, states=states, counties=counties, hospital_types=hospital_types)

# @app.route('/confirm_location', methods=['GET', 'POST'])
# @login_required
# def confirm_location():
#     city = request.args.get('city')
#     state = request.args.get('state')
#     if request.method == 'POST':
#         # Get the user's input for location confirmation
#         city = request.form['city']
#         state = request.form['state']
#         country = request.form['country']
        
#         # Debugging: Print the details being searched
#         print(f"Searching for city: {city}, state: {state}, country: {country}")

#         # Use the india_cities.csv data to find the latitude and longitude
#         latitude, longitude = find_lat_lon(city, state, country)
        
#         if latitude is not None and longitude is not None:
#             # Update session with the confirmed location
#             session['user_city'] = city
#             session['user_state'] = state
#             session['user_lat'] = latitude
#             session['user_lon'] = longitude
#             session['user_location_confirmed'] = True
#             print("Location found and session updated:", latitude, longitude)
#             # Redirect back to the location page to show hospitals
#             return redirect(url_for('location'))
#         else:
#             flash("Location could not be found in the database. Please try again.", "danger")
#             print("Location not found in india_cities.csv.")
    
#     return render_template('confirm_location.html', city=city, state=state)

# @app.route('/navigate')
# @login_required
# def navigate():
#     address = request.args.get('address')
#     city = request.args.get('city')
#     state = request.args.get('state')

#     # Geocode the hospital address to get latitude and longitude
#     geolocator = Nominatim(user_agent="oxyleap")
#     location = geolocator.geocode(f"{address}, {city}, {state}")

#     if location:
#         # Create a Folium map centered on the hospital location
#         hospital_map = folium.Map(location=[location.latitude, location.longitude], zoom_start=13)

#         # Add a marker for the hospital
#         folium.Marker([location.latitude, location.longitude], tooltip=f"{address}, {city}, {state}").add_to(hospital_map)

#         # Retrieve user location from session
#         user_lat = session.get('user_lat', 37.7749)
#         user_lon = session.get('user_lon', -122.4194)
#         folium.Marker([user_lat, user_lon], tooltip="User Location", icon=folium.Icon(color='green')).add_to(hospital_map)

#         # Add a route from user location to hospital
#         folium.PolyLine(locations=[[user_lat, user_lon], [location.latitude, location.longitude]], color="red").add_to(hospital_map)

#         # Render the map in the template
#         map_html = hospital_map._repr_html_()
#     else:
#         flash("Location not found.", "danger")
#         return redirect(url_for('location'))

#     return render_template('navigation.html', map_html=map_html)

# @app.route('/health_centers')
# @login_required
# def health_centers():
#     hospitals = get_hospitals()
#     return render_template('health_centers.html', hospitals=hospitals)

# @app.route('/emergency')
# @login_required
# def emergency():
#     hospitals = get_hospitals_with_emergency_services()
#     return render_template('emergency.html', hospitals=hospitals)

# @app.route('/acute_care')
# @login_required
# def acute_care():
#     hospitals = get_hospitals_by_type('Acute Care Hospitals')
#     return render_template('acute_care.html', hospitals=hospitals)

# @app.route('/critical_care')
# @login_required
# def critical_care():
#     hospitals = get_hospitals_by_type('Critical Access Hospitals')
#     return render_template('critical_care.html', hospitals=hospitals)

# @app.route('/childrens')
# @login_required
# def childrens():
#     hospitals = get_hospitals_by_type('Children\'s')
#     return render_template('childrens.html', hospitals=hospitals)

# @app.route('/psychiatric')
# @login_required
# def psychiatric():
#     hospitals = get_hospitals_by_type('Psychiatric')
#     return render_template('psychiatric.html', hospitals=hospitals)

# @app.route('/review/<hospital_id>', methods=['GET', 'POST'])
# @login_required
# def review(hospital_id):
#     hospital = get_hospital_by_id(hospital_id)
#     if request.method == 'POST':
#         review_text = request.form['review']
#         rating = request.form['rating']
#         add_review(hospital_id, review_text, rating)
#         return redirect(url_for('records'))
#     return render_template('review.html', hospital=hospital)

# @app.route('/records')
# @login_required
# def records():
#     reviews = get_reviews()
#     return render_template('records.html', reviews=reviews)

# # Train the Machine Learning Model
# def train_model(csv_path):
#     df = pd.read_csv(csv_path)
#     X = df[['year', 'month']]
#     y = df['active_beds']
#     X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
#     model = RandomForestClassifier()
#     model.fit(X_train, y_train)

#     # Update bed status in MongoDB
#     for i, row in df.iterrows():
#         hospital_id = row['facility_id']
#         status = model.predict([[row['year'], row['month']]])[0]
#         update_bed_status(hospital_id, status)

# if __name__ == '__main__':
#     import_hospital_dataset('data/hospital_dataset.csv')  # Import data from the CSV file
#     app.run(debug=True)
