import { useState } from "react";
import { Link } from "react-router-dom";
import { login, register } from "../lib/api";
import "./Auth.css";

function Auth({ mode, email, setEmail, onSuccess }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        onSuccess();
      } else {
        const result = await register(email, password);
        if (result.email) {
          onSuccess();
        } else {
          setError("Check your email to confirm your account, then log in.");
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <div className="card">
        <div className="brand">
          <h1 className="brand-title">Choreo Video Library</h1>
          <p className="brand-description">
            Upload a dance video and break down choreography with counts, custom
            looping/speed, mirroring, and side-by-side comparison.
          </p>
        </div>

        <h2 className="form-title">
          {mode === "login" ? "Log in" : "Sign up"}
        </h2>
        <form onSubmit={handleSubmit}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button type="submit" disabled={loading}>
            {loading
              ? "Please wait..."
              : mode === "login"
                ? "Log in"
                : "Sign up"}
          </button>
        </form>

        {error && <p className="error">{error}</p>}

        <p className="switch">
          {mode === "login" ? (
            <>
              Don't have an account? <Link to="/signup">Sign up</Link>
            </>
          ) : (
            <>
              Already have an account? <Link to="/">Log in</Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

export default Auth;
