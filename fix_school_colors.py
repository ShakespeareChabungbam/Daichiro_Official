import os
import glob

employee_dir = "app/templates/employee"
html_files = glob.glob(os.path.join(employee_dir, "*.html"))

replacements = {
    "school-navy": "zinc-900",
    "school-light": "zinc-800",
    "school-muted": "zinc-600",
    "school-text": "zinc-300",
    "school-gold": "amber-500",
    "school-mid": "zinc-700"
}

for filepath in html_files:
    with open(filepath, "r") as f:
        content = f.read()
        
    original = content
    for old, new in replacements.items():
        content = content.replace(old, new)
        
    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Fixed {filepath}")

print("Done!")
