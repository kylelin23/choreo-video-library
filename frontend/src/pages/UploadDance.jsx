import "../index.css";
import "./UploadDance.css";
import { logout as apiLogout } from "../lib/api";

function UploadDance({ email, onLogout, onUploadDance }) {
  const handleLogout = async () => {
    await apiLogout();
    onLogout();
  };

  return (
    <div className="page">
      <div className="home-card">
        <header className="home-header">
          <div>
            <h1>Choreo Video Library</h1>
            <p className="subtitle">
              {email ? `Signed in as ${email}` : "Welcome back"}
            </p>
          </div>
          <button className="logout-btn" onClick={handleLogout}>
            Log out
          </button>
        </header>

        <button className="upload-btn" onClick={onUploadDance}>
          Upload Dance
        </button>

        <section className="library">
          <h2>Previously Uploaded Dances</h2>
          <div className="library-empty">
            <p>No dances uploaded yet.</p>
          </div>
        </section>
      </div>
    </div>
  );
}

export default UploadDance;
