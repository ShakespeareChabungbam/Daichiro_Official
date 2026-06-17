import glob

files = [
    "app/templates/employee/booking_status.html",
    "app/templates/employee/pricing_management.html",
    "app/templates/employee/appointment_history.html",
    "app/templates/employee/skillnest_records.html",
    "app/templates/employee/skillnest_settings.html"
]

for f in files:
    try:
        with open(f, 'r') as fp:
            content = fp.read()
            
        # The back links typically look like:
        # class="inline-flex items-center gap-2 mb-6 text-xs font-bold text-zinc-400 hover:text-amber-500 transition-colors"
        # or hover:text-school-gold
        
        # We replace text-zinc-400 hover:text-school-gold with text-amber-500 hover:text-amber-400
        # Wait, my fix_school_colors.py already replaced school-gold with amber-500.
        content = content.replace("text-zinc-400 hover:text-amber-500", "text-amber-500 hover:text-amber-400")
        content = content.replace("text-zinc-400 hover:text-school-gold", "text-amber-500 hover:text-amber-400")
        
        with open(f, 'w') as fp:
            fp.write(content)
        print(f"Fixed {f}")
    except Exception as e:
        print(f"Error on {f}: {e}")
