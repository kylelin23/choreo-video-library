import { useState } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import Auth from "./Auth.jsx";
import UploadDance from "./UploadDance.jsx";
import Home from "./Home.jsx";
import "./App.css";

function App() {
  const [email, setEmail] = useState("");
  const navigate = useNavigate();

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
          <UploadDance
            email={email}
            onLogout={handleLogout}
            onUploadDance={() => navigate("/home")}
          />
        }
      />
      <Route path="/home" element={<Home />} />
    </Routes>
  );
}

export default App;
