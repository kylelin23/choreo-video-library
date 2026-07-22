from flask import Blueprint, request, jsonify, session
from apis.register import register
from apis.login import login
from apis.me import me
from apis.logout import logout

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/register', methods=['POST'])
def register_route():
    data = request.json
    supa_session, user, error = register(data["email"], data["password"])
    if error:
        return jsonify({"error": error}), 400

    if supa_session:
        session['supabase_token'] = supa_session.access_token
        session['user_id'] = user.id
        return jsonify({"email": user.email})

    return jsonify({"status": "check your email to confirm"})


@auth_bp.route('/api/auth/login', methods=['POST'])
def login_route():
    data = request.json
    supa_session, user, error = login(data["email"], data["password"])
    if error:
        return jsonify({"error": error}), 401

    session['supabase_token'] = supa_session.access_token
    session['user_id'] = user.id
    return jsonify({"email": user.email})


@auth_bp.route('/api/auth/me', methods=['GET'])
def me_route():
    result, error = me(session)
    if error:
        return jsonify({"error": error}), 401
    return jsonify(result)


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout_route():
    logout(session)
    return jsonify({"status": "logged out"})
