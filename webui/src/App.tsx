import { Routes, Route, Link, useLocation } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MissionsPage from "./pages/MissionsPage";
import MapsPage from "./pages/MapsPage";
import { AppBar, Toolbar, Typography, Box, Button } from "@mui/material";

export default function App() {
  const location = useLocation();
  return (
    <Box display="flex" flexDirection="column" height="100%">
      <AppBar position="static" color="primary">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            Mission Control
          </Typography>
          <Button
            component={Link}
            to="/"
            color={location.pathname === "/" ? "inherit" : "secondary"}
          >
            Dashboard
          </Button>
          <Button
            component={Link}
            to="/missions"
            color={location.pathname === "/missions" ? "inherit" : "secondary"}
          >
            Missions
          </Button>
          <Button
            component={Link}
            to="/maps"
            color={location.pathname === "/maps" ? "inherit" : "secondary"}
          >
            Maps
          </Button>
        </Toolbar>
      </AppBar>
      <Box flex={1} minHeight={0}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/missions" element={<MissionsPage />} />
          <Route path="/maps" element={<MapsPage />} />
        </Routes>
      </Box>
    </Box>
  );
}
