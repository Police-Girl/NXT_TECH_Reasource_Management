# create_admin.py - run once per admin:  python create_admin.py
# Admin accounts cannot be created from the website, only with this script.

import getpass

from models.user_model import create_user


def main():
    name = input("Full name: ").strip()
    work_id = input("Work ID: ").strip()
    email = input("Email (Gmail): ").strip()
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords do not match.")
        return
    if create_user(name, work_id, email, password, role="admin"):
        print(f"Admin account created for {name} ({work_id}).")
    else:
        print("That Work ID already exists.")


if __name__ == "__main__":
    main()
