# Blueprint for authentication routes — register, login, logout
from flask import Blueprint, render_template, request, redirect, flash, url_for
# werkzeug comes with Flask — handles password hashing
from werkzeug.security import generate_password_hash, check_password_hash
# Flask-Login handles session management (keeping users logged in)
from flask_login import login_user, logout_user, login_required, UserMixin
# Import get_container to access Cosmos DB
from db import get_container
import uuid

# Create the blueprint — 'auth' is its name, used when referencing routes
auth = Blueprint('auth', __name__)

# UserMixin gives our User class the methods Flask-Login needs
class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.name = user_data['name']
        self.work_id = user_data['work_id']
        self.role = user_data['role']
        self.email = user_data.get('email', '')

# Registration route
@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        work_id = request.form.get('work_id')
        password = request.form.get('password')
        role = request.form.get('role', 'staff')
        email = request.form.get('email')

        container = get_container('users')

        # Check if work_id already exists
        existing = list(container.query_items(
            query=f"SELECT * FROM c WHERE c.work_id = '{work_id}'",
            enable_cross_partition_query=True
        ))

        if existing:
            flash('Work ID already registered.', 'error')
            return redirect('/register')

        # Hash the password before saving — never store plain text
        user_data = {
            'id': str(uuid.uuid4()),
            'name': name,
            'work_id': work_id,
            'password': generate_password_hash(password),
            'role': role,
            'email': email, 
        }

        container.create_item(body=user_data)
        flash('Account created! Please log in.', 'success')
        return redirect('/login')

    return render_template('register.html')

# Login route
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        work_id = request.form.get('work_id')
        password = request.form.get('password')

        container = get_container('users')

        # Find user by work_id
        users = list(container.query_items(
            query=f"SELECT * FROM c WHERE c.work_id = '{work_id}'",
            enable_cross_partition_query=True
        ))

        if not users or not check_password_hash(users[0]['password'], password):
            flash('Invalid work ID or password.', 'error')
            return redirect('/login')

        # Log the user in
        user = User(users[0])
        login_user(user)
        flash(f'Welcome back, {user.name}!', 'success')

        # Redirect admins to admin dashboard, staff to landing page
        if user.role == 'admin':
            return redirect(url_for('admin'))

        return redirect('/')

    return render_template('login.html')

# Logout route
@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect('/login')