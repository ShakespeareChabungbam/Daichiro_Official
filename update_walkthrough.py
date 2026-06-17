import re

with open('.gemini/antigravity-ide/brain/e56f4f43-6ab3-4a08-a0e1-d9715a661a67/walkthrough.md', 'r') as f:
    content = f.read()

new_content = """# Employee Section Contrast Fix Walkthrough

I have completely aligned the `employee` section's CSS with the `admin` section to ensure perfect color contrast and layout consistency, exactly as requested.

## Changes Made
1. **Restored Global Tailwind Configuration**: Reverted `base_employee.html` to perfectly match the `admin` section's layout, removing the custom color overrides (like `school-*` colors and dark-blue hardcoded inputs) that were introduced previously. This guarantees the sidebar and main structure are exactly "like the admin section."
2. **Template Synchronization**: I programmatically synchronized the exact markup and CSS inline styles from the following Admin pages to their Employee counterparts:
   - `appointment_history.html`
   - `booking_status.html`
   - `pricing_management.html`
   - `skillnest_records.html`
   These pages now use the exact same high-contrast dark backgrounds and white text that are proven to be highly visible in the admin portal.
3. **Cleaned up Tailwind Classes**: Scanned all remaining employee-specific templates (like `assessments_create_client.html` and `skillnest_admissions.html`) and replaced the invalid `school-*` Tailwind classes with standard, high-contrast `zinc-*` and `amber-*` tokens, ensuring they render correctly on both light and dark backgrounds.
4. **Removed Fake Files**: Deleted non-functional fake templates (`appt_history.html`, `appt_booking_status.html`, `appt_pricing.html`) created in previous attempts, ensuring the server properly loads the correct template files.

## Verification
- Verified that all inputs in the `employee` section now inherit the correct theme background and color, avoiding the "invisible text" issue.
- Verified that the `has_permission` checks within the `employee` section remain fully intact, ensuring staff members only see what they are authorized to see.
"""

with open('.gemini/antigravity-ide/brain/e56f4f43-6ab3-4a08-a0e1-d9715a661a67/walkthrough.md', 'w') as f:
    f.write(new_content)

print("Updated walkthrough!")
