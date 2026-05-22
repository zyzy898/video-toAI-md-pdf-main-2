import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import LandingPage from './pages/LandingPage.jsx';
import ShowcasePage from './pages/ShowcasePage.jsx';
import NavBar from './components/NavBar.jsx';

/**
 * 路由 + 常驻顶栏。
 *  /          → 首页（着陆页 + DarkVeil + 开始演示按钮）
 *  /showcase  → 详细演示内容
 *  其它       → 重定向到 /
 *
 * <NavBar /> 放在 Routes 外，所以两个页面都会保留同一条顶栏。
 */
export default function App() {
  return (
    <BrowserRouter>
      <NavBar />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/showcase" element={<ShowcasePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
