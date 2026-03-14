import { useState } from "react";
import { useSelectionStore } from "../utils/state";
import { sendMissionInstant, sendMissionScheduled } from "../utils/api";
import { showToast } from "@/lib/toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Send } from "lucide-react";

export default function RightPanel() {
  const robotId = useSelectionStore((s) => s.selectedRobotId);
  const mapId = useSelectionStore((s) => s.selectedMapId);
  const destX = useSelectionStore((s) => s.destX);
  const destY = useSelectionStore((s) => s.destY);
  const [scheduledTime, setScheduledTime] = useState("");
  const [cron, setCron] = useState("");

  const ready = Boolean(robotId && mapId && destX != null && destY != null);

  const onSendInstant = async () => {
    if (!ready) {
      showToast("Select robot, map, and a valid destination", "warning");
      return;
    }
    try {
      await sendMissionInstant({
        robotId: robotId!,
        mapId: mapId!,
        x: destX!,
        y: destY!,
      });
      showToast("Mission sent", "success");
    } catch (e: any) {
      showToast(e?.message || "Send failed", "error");
    }
  };

  const onSendScheduled = async () => {
    if (!ready) {
      showToast("Select robot, map, and a valid destination", "warning");
      return;
    }
    if (!scheduledTime && !cron) {
      showToast("Provide scheduled time or cron", "warning");
      return;
    }
    try {
      await sendMissionScheduled({
        robotId: robotId!,
        mapId: mapId!,
        x: destX!,
        y: destY!,
        scheduledTime: scheduledTime || undefined,
        cron: cron || undefined,
      });
      showToast("Scheduled mission created", "success");
    } catch (e: any) {
      showToast(e?.message || "Schedule failed", "error");
    }
  };

  const coordFields = (
    <div className="grid grid-cols-2 md:grid-cols-1 gap-2">
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
          X (EPSG:25832)
        </Label>
        <Input
          readOnly
          value={destX ?? ""}
          className="font-mono text-sm bg-secondary/30 h-8"
        />
      </div>
      <div className="space-y-1">
        <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
          Y (EPSG:25832)
        </Label>
        <Input
          readOnly
          value={destY ?? ""}
          className="font-mono text-sm bg-secondary/30 h-8"
        />
      </div>
    </div>
  );

  return (
    <div className="p-3">
      <Tabs defaultValue="regular">
        <TabsList className="w-full bg-secondary/50">
          <TabsTrigger value="regular" className="flex-1 text-xs">
            Regular
          </TabsTrigger>
          <TabsTrigger value="scheduled" className="flex-1 text-xs">
            Scheduled
          </TabsTrigger>
          <TabsTrigger value="cron" className="flex-1 text-xs">
            CRON
          </TabsTrigger>
        </TabsList>

        <TabsContent value="regular" className="mt-3 space-y-3">
          {coordFields}
          <Button
            className="w-full gap-2"
            disabled={!ready}
            onClick={onSendInstant}
          >
            <Send className="h-4 w-4" />
            Send Mission
          </Button>
        </TabsContent>

        <TabsContent value="scheduled" className="mt-3 space-y-3">
          {coordFields}
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
              Scheduled Time
            </Label>
            <Input
              type="datetime-local"
              value={scheduledTime}
              onChange={(e) => setScheduledTime(e.target.value)}
              className="h-8 text-sm"
            />
          </div>
          <Button
            className="w-full gap-2"
            disabled={!ready}
            onClick={onSendScheduled}
          >
            <Send className="h-4 w-4" />
            Send Mission
          </Button>
        </TabsContent>

        <TabsContent value="cron" className="mt-3 space-y-3">
          {coordFields}
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground uppercase tracking-wider">
              CRON (m h dom mon dow)
            </Label>
            <Input
              placeholder="0 9 * * *"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              className="h-8 text-sm font-mono"
            />
          </div>
          <Button
            className="w-full gap-2"
            disabled={!ready}
            onClick={onSendScheduled}
          >
            <Send className="h-4 w-4" />
            Send Mission
          </Button>
        </TabsContent>
      </Tabs>
    </div>
  );
}
