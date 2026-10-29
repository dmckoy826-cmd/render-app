import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ModelsPage from "./pages/ModelsPage";
import ModelWorkspace from "./pages/ModelWorkspace";
import FinishesPage from "./pages/FinishesPage";
import PresetsPage from "./pages/PresetsPage";
import JobsPage from "./pages/JobsPage";
import GalleryPage from "./pages/GalleryPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/models" replace />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/models/:id" element={<ModelWorkspace />} />
        <Route path="/finishes" element={<FinishesPage />} />
        <Route path="/presets" element={<PresetsPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="*" element={<Navigate to="/models" replace />} />
      </Route>
    </Routes>
  );
}
