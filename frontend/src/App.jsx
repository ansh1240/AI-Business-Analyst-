import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";

import MainLayout from "./layouts/mainlayout";

import Dashboard from "./pages/dashboard";
import AutoDashboard from "./pages/AutoDashboard";
import UploadData from "./pages/uploaddata";
import DataProfile from "./pages/dataprofile";
import DataCleaning from "./pages/DataCleaning";
import Analysis from "./pages/analysis";
import Insights from "./pages/insights";
import WhatIf from "./pages/WhatIf";
import Forecast from "./pages/forecast";
import Reports from "./pages/reports";
import Login from "./pages/Login";
import Register from "./pages/Register";
function ProtectedRoute({ children }) {
  const token = localStorage.getItem("access_token");

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
function App() {
  return (
    <BrowserRouter>

      <Routes>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
<Route
  element={
    <ProtectedRoute>
      <MainLayout />
    </ProtectedRoute>
  }
>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/auto-dashboard" element={<AutoDashboard />} />
          <Route path="/upload" element={<UploadData />} />
          <Route path="/profile" element={<DataProfile />} />
          <Route path="/data-cleaning" element={<DataCleaning />} />
          <Route path="/analysis" element={<Analysis />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/what-if" element={<WhatIf />} />
          <Route path="/forecast" element={<Forecast />} />
          <Route path="/reports" element={<Reports />} />

        </Route>

        <Route
          path="*"
          element={<h1>404 - Page Not Found</h1>}
        />

      </Routes>

    </BrowserRouter>
  );
}

export default App;