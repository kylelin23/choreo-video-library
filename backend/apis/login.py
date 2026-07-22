from supabase_client import supabase
from supabase_auth.errors import AuthApiError

# Authenticates the user when they log in
def login(email, password):
    try:
        result = supabase.auth.sign_in_with_password(
            {"email": email, "password": password})
    except AuthApiError:
        return None, None, "invalid credentials"

    if result.session is None:
        return None, None, "invalid credentials"
    return result.session, result.user, None
