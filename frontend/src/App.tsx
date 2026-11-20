import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import RequireAuth from "./components/RequireAuth";
import EvalSets from "./pages/EvalSets";
import KnowledgeBaseDetail from "./pages/KnowledgeBaseDetail";
import KnowledgeBases from "./pages/KnowledgeBases";
import Login from "./pages/Login";
import Review from "./pages/Review";
import Scoreboard from "./pages/Scoreboard";
import DocumentsTab from "./pages/kb/DocumentsTab";
import KnowledgeTab from "./pages/kb/KnowledgeTab";
import SettingsTab from "./pages/kb/SettingsTab";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<Navigate to="/kbs" replace />} />
          <Route path="/kbs" element={<KnowledgeBases />} />
          <Route path="/kbs/:kbId" element={<KnowledgeBaseDetail />}>
            <Route index element={<Navigate to="documents" replace />} />
            <Route path="documents" element={<DocumentsTab />} />
            <Route path="knowledge" element={<KnowledgeTab />} />
            <Route path="evals" element={<EvalSets />} />
            <Route path="review" element={<Review />} />
            <Route path="scores" element={<Scoreboard />} />
            <Route path="settings" element={<SettingsTab />} />
          </Route>
          <Route path="*" element={<Navigate to="/kbs" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
