import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import RequireAuth from "./components/RequireAuth";
import KnowledgeBaseDetail from "./pages/KnowledgeBaseDetail";
import KnowledgeBases from "./pages/KnowledgeBases";
import Login from "./pages/Login";

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
          <Route path="/kbs/:kbId" element={<KnowledgeBaseDetail />} />
          <Route path="*" element={<Navigate to="/kbs" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
