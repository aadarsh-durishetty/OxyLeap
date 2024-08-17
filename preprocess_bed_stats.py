import os
import pandas as pd
from pymongo import MongoClient
from multiprocessing import Pool, cpu_count

# MongoDB Configuration
MONGO_URI = "mongodb://localhost:27017/oxyleap"
client = MongoClient(MONGO_URI)
db = client.oxyleap

# Function to process a single CSV file
def process_file(filename):
    facility_id = os.path.splitext(filename)[0]
    
    # Check if the facility_id already exists in MongoDB
    if db.bed_stats.find_one({'facility_id': facility_id}):
        print(f"Data for {facility_id} already exists in MongoDB. Skipping.")
        return None
    
    csv_path = os.path.join('data/bed_stats', filename)
    
    try:
        df = pd.read_csv(csv_path, sep=',')
        
        # Convert DataFrame to a list of dictionaries for MongoDB
        data = df.to_dict('records')
        
        # Prepare the document to insert
        document = {
            'facility_id': facility_id,
            'data': data
        }
        
        return document
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return None

# Preprocess bed statistics and load into MongoDB
def preprocess_bed_stats():
    bed_stats_dir = 'data/bed_stats'
    files = [f for f in os.listdir(bed_stats_dir) if f.endswith('.csv')]
    
    # Use multiprocessing to process files in parallel
    with Pool(cpu_count()) as pool:
        documents = pool.map(process_file, files)
    
    # Filter out any None results (from skipped or failed processing)
    documents = [doc for doc in documents if doc is not None]
    
    if documents:
        # Batch insert documents into MongoDB
        db.bed_stats.insert_many(documents, ordered=False)
        print(f"Inserted {len(documents)} new documents into MongoDB.")
    else:
        print("No new documents to insert. All data already exists in MongoDB.")

if __name__ == '__main__':
    preprocess_bed_stats()

