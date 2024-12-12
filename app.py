from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import os
import random
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///instance/santa.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    wishlist = db.Column(db.Text, nullable=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)

    @property
    def wishlist_items(self):
        if not self.wishlist:
            return []
        try:
            return json.loads(self.wishlist)
        except:
            return []

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists!')
            return redirect(url_for('register'))
        
        # Make the first user an admin
        is_admin = User.query.count() == 0
        user = User(username=username, password=password, is_admin=is_admin)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    assigned_person = None
    if current_user.assigned_to:
        assigned_person = User.query.get(current_user.assigned_to)
        if assigned_person and assigned_person.wishlist:
            try:
                assigned_person.wishlist = json.loads(assigned_person.wishlist)
            except:
                assigned_person.wishlist = []
    
    return render_template('dashboard.html', assigned_person=assigned_person)

@app.route('/update_wishlist', methods=['POST'])
@login_required
def update_wishlist():
    items = request.form.getlist('items[]')
    links = request.form.getlist('links[]')
    
    # Create a list of dictionaries with name and link
    wishlist = []
    for item, link in zip(items, links):
        if item.strip():  # Only add non-empty items
            wishlist.append({
                'name': item.strip(),
                'link': link.strip() if link.strip() else None
            })
    
    current_user.wishlist = json.dumps(wishlist)
    db.session.commit()
    flash('Wishlist updated successfully!')
    return redirect(url_for('dashboard'))

@app.route('/draw')
@login_required
def draw():
    if current_user.assigned_to:
        flash('You have already drawn a name!')
        return redirect(url_for('dashboard'))
    
    # Get all users who haven't been assigned to anyone yet
    available_users = User.query.filter(
        User.id != current_user.id,
        ~User.id.in_(db.session.query(User.assigned_to).filter(User.assigned_to != None))
    ).all()
    
    if not available_users:
        flash('No available users to draw!')
        return redirect(url_for('dashboard'))
    
    # Randomly select a user
    chosen_user = random.choice(available_users)
    current_user.assigned_to = chosen_user.id
    db.session.commit()
    
    flash(f'You have drawn a name! Check your dashboard to see their wishlist.')
    return redirect(url_for('dashboard'))

@app.route('/draw_names', methods=['POST'])
@login_required
def draw_names():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Only admins can draw names'})
    
    try:
        # Get all users
        users = User.query.all()
        if len(users) < 2:
            return jsonify({'success': False, 'message': 'Need at least 2 participants'})
        
        # Reset all assignments
        for user in users:
            user.assigned_to = None
        
        # Create a list of available recipients
        available_recipients = users.copy()
        
        # For each user, assign a random recipient
        for user in users:
            # Remove the current user from potential recipients
            valid_recipients = [r for r in available_recipients if r.id != user.id]
            
            if not valid_recipients:
                # If we can't find a valid recipient, reset and try again
                return jsonify({'success': False, 'message': 'Could not assign all Secret Santas. Please try again.'})
            
            # Randomly select a recipient
            recipient = random.choice(valid_recipients)
            user.assigned_to = recipient.id
            
            # Remove the selected recipient from available recipients
            available_recipients.remove(recipient)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Names drawn successfully!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
