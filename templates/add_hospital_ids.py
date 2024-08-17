import re

def generate_hospital_ids(input_file, output_file):
    with open(input_file, 'r') as f:
        content = f.read()

    # Regular expression to find each hospital section's title (inside <h1> tags)
    pattern = re.compile(r'(<div class="hospital-section">.*?<h1>)(.*?)(</h1>)', re.DOTALL)
    
    def add_id(match):
        # Extract the hospital name
        hospital_name = match.group(2).strip()
        # Convert the hospital name to lowercase and replace spaces with hyphens
        hospital_id = "hospital-" + re.sub(r'\s+', '-', hospital_name.lower())
        # Return the modified section with the new ID
        return f'<div class="hospital-section" id="{hospital_id}">{match.group(1)}{hospital_name}{match.group(3)}'
    
    # Replace each hospital section with a new one that includes an ID
    updated_content = pattern.sub(add_id, content)
    
    with open(output_file, 'w') as f:
        f.write(updated_content)

# Replace 'hospital_info.html' with the path to your input file
input_file = 'templates/hospital_info.html'
# Output file where the new content will be saved
output_file = 'hospital_info_with_ids.html'

generate_hospital_ids(input_file, output_file)
