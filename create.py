# scripts/create_admin.py
from getpass import getpass
from app import create_app
from app.extensions import db
from app.models.user import User


def main():
    app = create_app()
    with app.app_context():
        email = input("Admin email: ").strip().lower()
        name = input("Full name: ").strip()
        phone = input("Phone (optional): ").strip()
        password = getpass("Password: ")

        # Check existing
        if User.query.filter_by(email=email).first():
            print("User with that email already exists.")
            return

        user = User(name=name, email=email, phone=phone, role="admin", is_staff=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Admin user {email} created successfully.")

if __name__ == "__main__":
    main()
