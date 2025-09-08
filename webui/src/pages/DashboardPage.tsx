import { Box, Divider } from "@mui/material";
import TopBanner from "../ui/TopBanner";
import LeftCommands from "../ui/LeftCommands";
import RightPanel from "../ui/RightPanel";
import MapView from "../ui/MapView";

export default function DashboardPage() {
  return (
    <Box display="flex" flexDirection="column" height="100%">
      <TopBanner />
      <Divider />
      <Box
        display="grid"
        gridTemplateColumns={{ xs: "1fr", md: "280px 1fr 320px" }}
        gap={1}
        flex={1}
        minHeight={0}
      >
        <Box
          sx={{
            display: { xs: "none", md: "block" },
            borderRight: "1px solid #eee",
          }}
        >
          <LeftCommands />
        </Box>
        <Box>
          <MapView />
        </Box>
        <Box sx={{ borderLeft: "1px solid #eee" }}>
          <RightPanel />
        </Box>
      </Box>
    </Box>
  );
}
