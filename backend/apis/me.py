# Checks whether user is logged in
def me(session):
    if 'user_id' not in session:
        return None, "not logged in"
    return {"user_id": session['user_id']}, None