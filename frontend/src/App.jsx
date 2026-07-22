import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import Auth from "./pages/Auth.jsx";
import UploadDance from "./pages/UploadDance.jsx";
import Home from "./pages/Home.jsx";
import { me as apiMe } from "./lib/api";
import "./index.css";

function App() {
  const [email, setEmail] = useState("");
  const [checkedSession, setCheckedSession] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    apiMe()
      .then((data) => setEmail(data.email || ""))
      .catch(() => {})
      .finally(() => setCheckedSession(true));
  }, []);

  if (!checkedSession) {
    return null; 
  }

  const handleLogout = () => {
    setEmail("");
    navigate("/");
  };

  return (
    <Routes>
      <Route
        path="/"
        element={
          <Auth
            mode="login"
            email={email}
            setEmail={setEmail}
            onSuccess={() => navigate("/upload-dance")}
          />
        }
      />
      <Route
        path="/signup"
        element={
          <Auth
            mode="signup"
            email={email}
            setEmail={setEmail}
            onSuccess={() => navigate("/upload-dance")}
          />
        }
      />
      <Route
        path="/upload-dance"
        element={
          email ? (
            <UploadDance
              email={email}
              onLogout={handleLogout}
              onUploadDance={() => navigate("/home")}
            />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route path="/home" element={<Home />} />
    </Routes>
  );
}

export default App;
