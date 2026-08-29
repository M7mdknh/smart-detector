import { Navigate, Route, Routes } from "react-router-dom";
import { DashboardPage } from "./dashboard/DashboardPage";
import { SimulationPage } from "./simulation/SimulationPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/simulation" element={<SimulationPage />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
