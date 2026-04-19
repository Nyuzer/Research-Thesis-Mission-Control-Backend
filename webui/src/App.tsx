import { Routes, Route, Link, useLocation, Navigate } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MissionsPage from "./pages/MissionsPage";
import MapsPage from "./pages/MapsPage";
import LoginPage from "./pages/LoginPage";
import UsersPage from "./pages/UsersPage";
import StatisticsPage from "./pages/StatisticsPage";
import MapGenPage from "./pages/MapGenPage";
import ProtectedRoute from "./components/ProtectedRoute";
import { cn } from "@/lib/utils";
import { useTheme } from "@/lib/theme";
import { useAuthStore } from "@/utils/auth";
import { LayoutDashboard, ListChecks, Map, Sun, Moon, Users, LogOut, BarChart3, PenTool } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function App() {
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const { isAuthenticated, user, logout } = useAuthStore();

  if (!isAuthenticated && location.pathname !== "/login") {
    return <Navigate to="/login" replace />;
  }

  if (location.pathname === "/login") {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    );
  }

  const navItems = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, match: (p: string) => p === "/" },
    { to: "/missions", label: "Missions", icon: ListChecks, match: (p: string) => p === "/missions" },
    { to: "/maps", label: "Maps", icon: Map, match: (p: string) => p === "/maps" },
    { to: "/statistics", label: "Statistics", icon: BarChart3, match: (p: string) => p === "/statistics" },
    ...(user?.role !== "viewer"
      ? [{ to: "/mapgen", label: "Map Gen", icon: PenTool, match: (p: string) => p === "/mapgen" }]
      : []),
    ...(user?.role === "admin"
      ? [{ to: "/users", label: "Users", icon: Users, match: (p: string) => p === "/users" }]
      : []),
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center justify-between px-2 sm:px-4 h-12 sm:h-14 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-cyan animate-pulse-glow" />
          <h1 className="text-sm sm:text-base font-semibold tracking-tight text-foreground">
            Mission Control
          </h1>
        </div>
        <div className="flex items-center gap-0.5 sm:gap-1">
          <nav className="flex items-center gap-0.5 sm:gap-1">
            {navItems.map(({ to, label, icon: Icon, match }) => {
              const active = match(location.pathname);
              return (
                <Link
                  key={to}
                  to={to}
                  className={cn(
                    "flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                    active
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent"
                  )}
                >
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{label}</span>
                </Link>
              );
            })}
          </nav>
          <span className="hidden sm:inline text-xs text-muted-foreground ml-2">
            {user?.username}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 ml-1"
            onClick={toggle}
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={logout}
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </header>
      {/* Content */}
      <div className="flex-1 min-h-0 overflow-auto md:overflow-hidden">
        <Routes>
          <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/missions" element={<ProtectedRoute><MissionsPage /></ProtectedRoute>} />
          <Route path="/maps" element={<ProtectedRoute><MapsPage /></ProtectedRoute>} />
          <Route path="/statistics" element={<ProtectedRoute><StatisticsPage /></ProtectedRoute>} />
          <Route path="/mapgen" element={<ProtectedRoute>{user?.role === "viewer" ? <Navigate to="/" replace /> : <MapGenPage />}</ProtectedRoute>} />
          <Route path="/users" element={<ProtectedRoute><UsersPage /></ProtectedRoute>} />
          <Route path="/login" element={<LoginPage />} />
        </Routes>
      </div>
    </div>
  );
}
