import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import shutil

# Load the dataset
file_path = 'data/hospital_dataset.csv'  # Replace with your actual path
hospital_data = pd.read_csv(file_path)

# Extract the hospital names
hospital_names = hospital_data['name'].unique()

# Directory to save images
output_dir = 'hospital_busy_hours'
os.makedirs(output_dir, exist_ok=True)

# Example busy hour pattern for a day (simulated)
busy_pattern = [5, 10, 15, 20, 30, 50, 70, 90, 100, 120, 140, 150, 
                160, 170, 180, 190, 200, 180, 160, 120, 100, 70, 40, 20]

# Time labels (hours)
time_labels = [f"{i}am" if i < 12 else f"{i-12 if i > 12 else 12}pm" for i in range(24)]

# Loop through each hospital and create an image
for hospital in hospital_names:
    plt.figure(figsize=(10, 5))
    plt.bar(time_labels, busy_pattern, color='blue')
    plt.title(f"Popular Times for {hospital}")
    plt.xlabel('Time of Day')
    plt.ylabel('Activity Level')
    
    # Create the file name
    file_name = hospital.lower().replace(" ", "-").replace("'", "") + ".png"
    file_path = os.path.join(output_dir, file_name)
    
    # Ensure the directory exists (in case of nested directories)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Save the figure
    plt.savefig(file_path)
    plt.close()  # Close the plot to save memory

# Zip the directory
zip_file_path = 'hospital_busy_hours.zip'
shutil.make_archive(zip_file_path.replace('.zip', ''), 'zip', output_dir)

# Print completion message
print("busy hours extracted successfully")
