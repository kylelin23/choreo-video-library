from supabase_client import supabase
from supabase_auth.errors import AuthApiError, AuthWeakPasswordError

# Registers the user when they sign in for the first time
def register(email, password):
    try:
        result = supabase.auth.sign_up({"email": email, "password": password})
    except AuthWeakPasswordError:
        return None, None, "password is too weak (needs at least 6 characters)"
    except AuthApiError as e:
        return None, None, str(e)

    if result.user is None:
        return None, None, "signup failed"
    return result.session, result.user, None