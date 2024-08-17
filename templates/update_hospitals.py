# import re

# def escape_jinja_string(s):
#     """Escape special characters for Jinja2 template."""
#     return s.replace("'", "\\'").replace('"', '\\"')

# def update_hospital_sections(input_file, output_file):
#     with open(input_file, 'r') as f:
#         content = f.read()

#     # Regular expression to find each hospital section
#     pattern = re.compile(r'(<div class="hospital-section">.*?<h1>)(.*?)(</h1>.*?</div>)', re.DOTALL)
    
#     sections = []
    
#     def add_id_and_class(match):
#         # Extract the hospital name
#         hospital_name = match.group(2).strip()
#         # Convert the hospital name to lowercase and replace spaces with hyphens
#         hospital_id = hospital_name.replace(' ', '-').replace("'", "").lower()
#         # Escape the hospital name for Jinja2
#         escaped_hospital_name = escape_jinja_string(hospital_id)
#         # Create the section with conditional rendering
#         section = f'{{% if hospital_name == \'{escaped_hospital_name}\' %}}<div class="hospital-section" id="hospital-{hospital_id}">{match.group(1)}{hospital_name}{match.group(3)}</div>{{% endif %}}'
#         sections.append(section)
#         return section
    
#     # Apply the transformation
#     pattern.sub(add_id_and_class, content)
    
#     with open(output_file, 'w') as f:
#         f.write('\n'.join(sections))

# # Replace 'hospital_info.html' with the path to your input file
# input_file = 'hospital_info.html'
# # Output file where the new content will be saved
# output_file = 'hospital_about_filtered.html'

# update_hospital_sections(input_file, output_file)
