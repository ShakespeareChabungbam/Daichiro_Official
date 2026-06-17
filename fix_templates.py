import os

admin_dir = "app/templates/admin"
employee_dir = "app/templates/employee"

files_to_sync = [
    "appointment_history.html",
    "booking_status.html",
    "pricing_management.html",
    "skillnest_records.html"
]

for f in files_to_sync:
    admin_path = os.path.join(admin_dir, f)
    emp_path = os.path.join(employee_dir, f)
    
    if os.path.exists(admin_path):
        with open(admin_path, 'r') as fp:
            content = fp.read()
            
        content = content.replace('{% extends "admin/base_admin.html" %}', '{% extends "employee/base_employee.html" %}')
        content = content.replace("url_for('admin.", "url_for('employee.")
        content = content.replace("session.admin_username", "emp.name")
        
        with open(emp_path, 'w') as fp:
            fp.write(content)
            
print("Synced files successfully!")
