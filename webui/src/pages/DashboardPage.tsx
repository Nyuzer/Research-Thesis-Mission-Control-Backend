import TopBanner from "../ui/TopBanner";
import RightPanel from "../ui/RightPanel";
import MapView from "../ui/MapView";
import { Separator } from "@/components/ui/separator";

export default function DashboardPage() {
  return (
    <div className="flex flex-col h-full md:h-full">
      <TopBanner />
      <Separator />
      {/* Desktop: side-by-side. Mobile: stacked with map on top */}
      <div className="flex flex-col md:grid md:grid-cols-[1fr_340px] flex-1 min-h-0">
        <div className="min-h-[300px] md:min-h-0 h-[50vh] md:h-auto">
          <MapView />
        </div>
        <div className="border-t md:border-t-0 md:border-l border-border">
          <RightPanel />
        </div>
      </div>
    </div>
  );
}
