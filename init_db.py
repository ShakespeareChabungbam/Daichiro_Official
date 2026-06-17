from app import create_app
from app.extensions import db, bcrypt
from app.models import Admin

app = create_app()

def init_db():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if admin already exists
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            hashed_pw = bcrypt.generate_password_hash('password123').decode('utf-8')
            new_admin = Admin(username='admin', password_hash=hashed_pw)
            db.session.add(new_admin)
            db.session.commit()
            print("Database initialized and 'admin' user created with password 'password123'.")
        else:
            print("Database already initialized. Admin exists.")

if __name__ == '__main__':
    init_db()
