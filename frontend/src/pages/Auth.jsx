import { Link } from "react-router-dom";
import "../index.css";
import "./Auth.css";

function Auth({ mode, email, setEmail, onSuccess }) {
  const handleSubmit = (e) => {
    e.preventDefault();
    // no real auth
    onSuccess();
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
          <input type="password" placeholder="Password" required />
          <button type="submit">
            {mode === "login" ? "Log in" : "Sign up"}
          </button>
        </form>
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
