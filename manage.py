# Filepath: manage.py

import sys
from tubealgo import create_app, db
from tubealgo.models import User

app = create_app()

def make_admin(email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_admin = True
            db.session.commit()
            print(f"Success! User '{email}' is now an admin.")
        else:
            print(f"Error: User with email '{email}' not found.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Please provide an email address.")
        print("Usage: python manage.py your-email@example.com")
    else:
        user_email = sys.argv[1]
        make_admin(user_email)
