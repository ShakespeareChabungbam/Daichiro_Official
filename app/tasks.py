from datetime import datetime, timedelta, timezone
import logging

def delete_old_clients(app):
    """
    Background task to delete clients older than 3 hours.
    Takes the app instance to run within the app context.
    """
    with app.app_context():
        from app.extensions import db
        from app.models import Client
        
        from app.models import StudentAssessment

        try:
            threshold = datetime.now(timezone.utc) - timedelta(hours=3)
            # Find all clients older than 3 hours
            old_clients = Client.query.filter(Client.created_at < threshold).all()
            count = len(old_clients)
            
            for client in old_clients:
                # Also delete associated in-progress assessment to avoid orphans
                orphaned_assessment = StudentAssessment.query.filter_by(
                    client_username=client.username,
                    status='in_progress'
                ).first()
                if orphaned_assessment:
                    db.session.delete(orphaned_assessment)
                
                db.session.delete(client)
                
            if count > 0:
                db.session.commit()
                logging.info(f"Deleted {count} stale client accounts.")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error deleting old clients: {e}")


def delete_old_assessments(app):
    """
    Background task to delete student assessments older than 3 months (90 days).
    """
    with app.app_context():
        from app.extensions import db
        from app.models import StudentAssessment

        try:
            threshold = datetime.now(timezone.utc) - timedelta(days=90)
            old_assessments = StudentAssessment.query.filter(StudentAssessment.created_at < threshold).all()
            count = len(old_assessments)

            for assessment in old_assessments:
                db.session.delete(assessment)

            if count > 0:
                db.session.commit()
                logging.info(f"Deleted {count} assessments older than 3 months.")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error deleting old assessments: {e}")


def delete_old_appointments(app):
    """
    Background task to delete appointments older than 3 months (90 days).
    """
    with app.app_context():
        from app.extensions import db
        from app.models import Appointment

        try:
            threshold = datetime.now(timezone.utc) - timedelta(days=90)
            old_appointments = Appointment.query.filter(Appointment.created_at < threshold).all()
            count = len(old_appointments)

            for appointment in old_appointments:
                db.session.delete(appointment)

            if count > 0:
                db.session.commit()
                logging.info(f"Deleted {count} appointments older than 3 months.")
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error deleting old appointments: {e}")

