# tubealgo/auth_local.py

from flask import render_template, request, redirect, url_for, flash, Blueprint, session
from flask_login import login_user, logout_user, current_user, login_required
from .models import User
from .forms import SignupForm, LoginForm
from .services import user_service

auth_local_bp = Blueprint('auth_local', __name__)

@auth_local_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    
    form = SignupForm()
    if form.validate_on_submit():
        referral_code = session.pop('referral_code', None)
        new_user, message, category = user_service.create_new_user(
            email=form.email.data, 
            password=form.password.data, 
            referred_by_code=referral_code
        )
        if not new_user:
            flash(message, category)
            return redirect(url_for('auth_local.signup'))
        
        flash(message, category)
        return redirect(url_for('auth_local.login'))
        
    return render_template('signup.html', form=form)

@auth_local_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'error')
            
    return render_template('login.html', form=form)

@auth_local_bp.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('core.home'))