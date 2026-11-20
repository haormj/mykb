import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import EvalSets from "./pages/EvalSets";
import Review from "./pages/Review";
import Scoreboard from "./pages/Scoreboard";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/evals" replace />} />
          <Route path="/evals" element={<EvalSets />} />
          <Route path="/review" element={<Review />} />
          <Route path="/scores" element={<Scoreboard />} />
          <Route path="*" element={<Navigate to="/evals" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
