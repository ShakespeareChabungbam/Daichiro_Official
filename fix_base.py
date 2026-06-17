import re

path = "app/templates/employee/base_employee.html"
with open(path, "r") as f:
    content = f.read()

# 1. Remove school colors from tailwind config
content = re.sub(r"\s*'school-gold':\s*'#C9A84C',.*?'school-mid':\s*'#E8ECF0',", "", content, flags=re.DOTALL)

# 2. Remove the inline styles added by previous agent
content = re.sub(r"/\* ── Global Form Input Overrides ── \*/.*?</style>", "</style>", content, flags=re.DOTALL)
content = re.sub(r"/\* ── Main content default text.*?</style>", "</style>", content, flags=re.DOTALL)

# 3. Restore the h2 color inline style (if it exists) to just class text-zinc-900 or text-white
content = re.sub(r'style="color:#0C2547;"', 'class="text-zinc-900"', content)

with open(path, "w") as f:
    f.write(content)

print("Fixed base_employee.html!")
