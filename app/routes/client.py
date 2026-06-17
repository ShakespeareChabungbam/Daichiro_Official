from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.models import Client, StudentAssessment, SiteConfig
from app.extensions import db, csrf
import json
import os
import base64

client_bp = Blueprint('client', __name__)

@client_bp.before_request
def require_login():
    # Allow login page and CSRF-exempt JSON API endpoints without a session redirect
    api_endpoints = {'client.login', 'client.assessment_autosave', 'client.assessment_scan_photo'}
    if request.endpoint in api_endpoints:
        return  # no session check needed; autosave/scan-photo check session internally
    if 'admin_id' in session:
        return redirect(url_for('admin.dashboard'))
    if 'client_id' not in session:
        return redirect(url_for('client.login'))

@client_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        from app.extensions import bcrypt
        client_user = Client.query.filter_by(username=username).first()
        if client_user and bcrypt.check_password_hash(client_user.password_hash, password):
            session['client_id'] = client_user.id
            session['client_username'] = client_user.username
            return redirect(url_for('client.assessment'))
            
        flash('Invalid Client Credentials. Your session may have expired.', 'error')
        
    return render_template('client/login.html')


@client_bp.route('/assessment/scan-photo', methods=['POST'])
@csrf.exempt
def assessment_scan_photo():
    """Accept a photo of the paper questionnaire and extract data via Gemini Vision."""
    if 'client_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    photo = request.files.get('photo')
    if not photo or photo.filename == '':
        return jsonify({'error': 'No photo provided'}), 400

    api_key = SiteConfig.get('gemini_api_key') or os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'no_api_key', 'message': 'Gemini API key not configured. Please contact the academy.'}), 503

    try:
        from google import genai
        from google.genai import types as genai_types
        from PIL import Image
        import io

        # Read and compress the image
        img_data = photo.read()
        try:
            img = Image.open(io.BytesIO(img_data))
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            if max(img.width, img.height) > 1600:
                ratio = 1600 / max(img.width, img.height)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=88, optimize=True)
            img_data = output.getvalue()
        except Exception:
            pass  # Use raw data if Pillow fails

        client = genai.Client(api_key=api_key)
        gemini_model = SiteConfig.get('gemini_model') or 'gemini-2.0-flash'

        prompt = """You are an expert OCR system reading a handwritten "Student Career Interest & Aptitude Questionnaire" from Daichiro Professional Skills Academy.

Extract ALL data into this EXACT JSON structure. Read handwriting carefully. For checkboxes, look for tick marks, filled circles, or any marking.

For Section C (Aptitude), the student fills circles under 1-5. Find which column is marked for each row.

Return ONLY valid JSON (no markdown, no explanation):
{
  "personal_info": {
    "full_name": "",
    "class_grade": "",
    "school_name": "",
    "contact_number": "",
    "email": ""
  },
  "interests": {
    "activities": [],
    "subjects": [],
    "professions": []
  },
  "aptitude": {
    "logical": "3",
    "science": "3",
    "writing": "3",
    "computers": "3",
    "design": "3",
    "speaking": "3",
    "planning": "3",
    "helping": "3",
    "tech": "3"
  },
  "personality": [],
  "career_vision": {
    "current_careers": "",
    "five_year_goals": "",
    "ideal_life": ""
  }
}

EXACT names for activities: "Solving math problems or puzzles", "Drawing, painting, or designing", "Writing stories or essays", "Playing computer games or coding", "Helping others with their problems", "Working with tools or machines", "Participating in debates or public speaking", "Taking care of animals or nature", "Organizing events or planning tasks", "Selling or promoting products/services"

EXACT names for subjects: "Mathematics", "Science - Physics", "Chemistry", "Biology", "English", "Languages", "Computer Science", "IT", "Social Science", "History", "Business Studies", "Economics", "Art", "Music", "Drama", "Physical Education", "Environmental Studies"

EXACT names for professions: "Doctor / Nurse", "Engineer / Scientist", "Teacher / Professor", "Artist / Designer", "Business Owner / Entrepreneur", "Lawyer / Judge", "Software Developer / Game Designer", "Police / Army Officer", "Social Worker / Counselor", "YouTuber / Influencer / Filmmaker"

EXACT personality statements: "I enjoy solving problems or challenges", "I like to express myself creatively", "I prefer working independently", "I like working with others in a team", "I care about helping people and making a difference", "I like leading and taking responsibility", "I enjoy experimenting and learning how things work", "I like keeping things organized and structured", "I enjoy physical activity or outdoor work"

Return ONLY the JSON object."""

        response = client.models.generate_content(
            model=gemini_model,
            contents=[
                prompt,
                genai_types.Part.from_bytes(data=img_data, mime_type='image/jpeg')
            ]
        )

        text = response.text.strip()
        # Strip markdown code fences
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()
        if text.endswith('```'):
            text = text[:-3].strip()

        extracted = json.loads(text)
        return jsonify({'success': True, 'data': extracted})

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f"Scan failed: {e}", exc_info=True)
        str_e = str(e)
        if '503' in str_e or 'UNAVAILABLE' in str_e or 'high demand' in str_e.lower():
            return jsonify({'error': 'High Demand', 'message': 'Google Gemini API is currently experiencing high demand. Please try uploading the image again later or fill in manually.'}), 503
        return jsonify({'error': 'Scan failed', 'message': 'Scan failed due to an internal error. Please try again or fill in manually.'}), 500


@client_bp.route('/assessment/autosave', methods=['POST'])
@csrf.exempt
def assessment_autosave():
    """Auto-save one section at a time. Personal info saved on step 1 — never lost."""
    try:
        data = request.json
        section = data.get('section')      # e.g. 'personal_info', 'interests', etc.
        section_data = data.get('data')    # the section's field values
        step = data.get('step', 1)         # current step number (1-5)
        
        client_username = session.get('client_username')
        if not client_username:
            return jsonify({'error': 'Not logged in'}), 401
        
        # Find existing in-progress assessment or create new one
        assessment = StudentAssessment.query.filter_by(
            client_username=client_username,
            status='in_progress'
        ).first()
        
        if not assessment:
            assessment = StudentAssessment(
                client_username=client_username,
                status='in_progress',
                current_step=1
            )
            db.session.add(assessment)
        
        # Save the specific section
        if section == 'personal_info':
            assessment.personal_info = section_data
        elif section == 'interests':
            assessment.interests = section_data
        elif section == 'aptitude':
            assessment.aptitude = section_data
        elif section == 'personality':
            assessment.personality = section_data
        elif section == 'career_vision':
            assessment.career_vision = json.dumps(section_data) if isinstance(section_data, dict) else str(section_data)
        elif section == 'final_submit':
            # If no in-progress assessment exists (e.g. session resumed), still return success
            if not assessment:
                session.clear()
                return jsonify({'success': True, 'submitted': True})
            # Save career vision if provided, then mark as submitted
            if section_data and isinstance(section_data, dict):
                assessment.career_vision = json.dumps(section_data)
            assessment.status = 'submitted'
            assessment.current_step = 5
            # Self-Destruct Client Credential in same transaction
            client_id = session.get('client_id')
            if client_id:
                client_user = db.session.get(Client, client_id)
                if client_user:
                    db.session.delete(client_user)
            db.session.commit()  # single commit for assessment + client deletion
            session.clear()
            return jsonify({'success': True, 'submitted': True})
        elif section == 'progress_only':
            pass  # Just update the step
        
        # Update progress (only advance, never go backwards)
        if step > (assessment.current_step or 1):
            assessment.current_step = step
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'saved_section': section,
            'step': step,
            'assessment_id': assessment.id
        })
        
    except Exception as e:
        db.session.rollback()
        from flask import current_app
        current_app.logger.error(f"Assessment error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@client_bp.route('/assessment', methods=['GET', 'POST'])
def assessment():
    if request.method == 'POST':
        try:
            data = request.json
            personal_info = data.get('personal_info', {})
            interests = data.get('interests', {})
            aptitude = data.get('aptitude', {})
            personality = data.get('personality', [])
            career_vision = data.get('career_vision', {})
            
            client_username = session.get('client_username')
            
            # Find existing in-progress assessment (from auto-save) or create new
            assessment = StudentAssessment.query.filter_by(
                client_username=client_username,
                status='in_progress'
            ).first()
            
            if assessment:
                # Update with final data
                assessment.personal_info = personal_info
                assessment.interests = interests
                assessment.aptitude = aptitude
                assessment.personality = personality
                assessment.career_vision = json.dumps(career_vision) if isinstance(career_vision, dict) else str(career_vision)
                assessment.current_step = 5
            else:
                # Create fresh (rare — means autosave wasn't used)
                assessment = StudentAssessment(
                    client_username=client_username,
                    personal_info=personal_info,
                    interests=interests,
                    aptitude=aptitude,
                    personality=personality,
                    career_vision=json.dumps(career_vision) if isinstance(career_vision, dict) else str(career_vision),
                    current_step=5
                )
                db.session.add(assessment)

            assessment.status = 'submitted'

            # Self-Destruct Client Credential in same transaction
            client_id = session.get('client_id')
            if client_id:
                client_user = db.session.get(Client, client_id)
                if client_user:
                    db.session.delete(client_user)

            db.session.commit()
            session.clear()
            
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            from flask import current_app
            current_app.logger.error(f"Assessment submission error: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    # GET request — check for in-progress assessment to resume
    client_username = session.get('client_username')
    saved_data = None
    resume_step = 0
    
    if client_username:
        existing = StudentAssessment.query.filter_by(
            client_username=client_username,
            status='in_progress'
        ).first()
        
        if existing:
            # Parse career_vision back to dict if needed
            cv = existing.career_vision
            if isinstance(cv, str):
                try:
                    cv = json.loads(cv)
                except (json.JSONDecodeError, TypeError):
                    cv = {}
            
            saved_data = {
                'personal_info': existing.personal_info or {},
                'interests': existing.interests or {},
                'aptitude': existing.aptitude or {},
                'personality': existing.personality or [],
                'career_vision': cv or {}
            }
            resume_step = (existing.current_step or 1) - 1  # 0-indexed for JS
            
    return render_template('client/assessment.html',
                          saved_data=saved_data,
                          resume_step=resume_step)
