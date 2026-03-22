import { useState } from "react";
import { useSelectionStore } from "../utils/state";
import {
  sendMissionInstant, sendMissionScheduled,
  sendAdvancedMission, fetchMissionTemplates,
} from "../utils/api";
import { showToast } from "@/lib/toast";
import { useAuthStore } from "@/utils/auth";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Send, Trash2, Plus, ChevronUp, ChevronDown, X, BookOpen } from "lucide-react";

export default function RightPanel() {
  const robotId = useSelectionStore((s) => s.selectedRobotId);
  const mapId = useSelectionStore((s) => s.selectedMapId);
  const destX = useSelectionStore((s) => s.destX);
  const destY = useSelectionStore((s) => s.destY);
  const [scheduledTime, setScheduledTime] = useState("");
  const [cron, setCron] = useState("");

  // Advanced mission state
  interface Step { action: string; x?: number; y?: number; duration?: number; zoneId?: string }
  const [advSteps, setAdvSteps] = useState<Step[]>([]);
  const [advName, setAdvName] = useState("");
  const [advSaveTemplate, setAdvSaveTemplate] = useState(false);
  const [advTemplateName, setAdvTemplateName] = useState("");
  const [templates, setTemplates] = useState<any[]>([]);

  const addStep = (action: string) => {
    if (action === "MOVE_TO" && destX != null && destY != null) {
      setAdvSteps((s) => [...s, { action: "MOVE_TO", x: destX!, y: destY! }]);
    } else if (action === "WAIT") {
      setAdvSteps((s) => [...s, { action: "WAIT", duration: 30 }]);
    } else if (action === "PARK") {
      setAdvSteps((s) => [...s, { action: "PARK", zoneId: "" }]);
    }
  };

  const removeStep = (i: number) => setAdvSteps((s) => s.filter((_, idx) => idx !== i));
  const moveStep = (i: number, dir: -1 | 1) => {
    setAdvSteps((s) => {
      const arr = [...s];
      const j = i + dir;
      if (j < 0 || j >= arr.length) return arr;
      [arr[i], arr[j]] = [arr[j], arr[i]];
      return arr;
    });
  };

  const onSendAdvanced = async () => {
    if (!robotId || !mapId || advSteps.length === 0) {
      showToast("Select robot, map, and add steps", "warning");
      return;
    }
    try {
      const steps = advSteps.map((s, i) => ({
        stepId: `step_${i}`,
        action: s.action,
        waypoint: s.x != null ? { type: "Point", coordinates: [s.x, s.y, 0] } : undefined,
        duration: s.duration,
        zoneId: s.zoneId || undefined,
        order: i,
      }));
      await sendAdvancedMission({
        robotId: robotId!,
        mapId: mapId!,
        name: advName || undefined,
        steps,
        saveAsTemplate: advSaveTemplate,
        templateName: advTemplateName || undefined,
      });
      showToast("Advanced mission sent", "success");
      setAdvSteps([]);
      setAdvName("");
    } catch (e: any) {
      showToast(e?.message || "Failed to send mission", "error");
    }
  };

  const loadTemplates = async () => {
    try {
      const t = await fetchMissionTemplates();
      setTemplates(t || []);
    } catch {}
  };

  const loadTemplate = (t: any) => {
    setAdvName(t.name);
    setAdvSteps(
      (t.steps || []).map((s: any) => ({
        action: s.action,
        x: s.waypoint?.coordinates?.[0],
        y: s.waypoint?.coordinates?.[1],
        duration: s.duration,
        zoneId: s.zoneId,
      }))
    );
  };

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
          <TabsTrigger value="advanced" className="flex-1 text-xs">
            Advanced
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

        <TabsContent value="advanced" className="mt-3 space-y-3">
          <Input
            placeholder="Mission name"
            value={advName}
            onChange={(e) => setAdvName(e.target.value)}
            className="h-8 text-sm"
          />

          {/* Steps list */}
          <div className="space-y-1.5 max-h-48 overflow-y-auto">
            {advSteps.map((step, i) => (
              <div key={i} className="flex items-center gap-1 bg-secondary/30 rounded-md px-2 py-1.5 text-xs">
                <span className="text-muted-foreground w-4">{i + 1}.</span>
                <span className="text-foreground font-medium flex-1">
                  {step.action === "MOVE_TO" && `MOVE (${step.x?.toFixed(0)}, ${step.y?.toFixed(0)})`}
                  {step.action === "WAIT" && (
                    <>
                      WAIT{" "}
                      <input
                        type="number"
                        value={step.duration || 30}
                        onChange={(e) => {
                          const val = parseInt(e.target.value) || 0;
                          setAdvSteps((s) => s.map((st, idx) => idx === i ? { ...st, duration: val } : st));
                        }}
                        className="w-12 bg-background border border-border rounded px-1 text-xs inline"
                      />
                      s
                    </>
                  )}
                  {step.action === "PARK" && "PARK"}
                </span>
                <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => moveStep(i, -1)}><ChevronUp className="h-3 w-3" /></Button>
                <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => moveStep(i, 1)}><ChevronDown className="h-3 w-3" /></Button>
                <Button variant="ghost" size="icon" className="h-5 w-5 text-red-400" onClick={() => removeStep(i)}><X className="h-3 w-3" /></Button>
              </div>
            ))}
          </div>

          {/* Add step buttons */}
          <div className="flex gap-1">
            <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={() => addStep("MOVE_TO")} disabled={destX == null}>
              <Plus className="h-3 w-3 mr-1" /> Move
            </Button>
            <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={() => addStep("WAIT")}>
              <Plus className="h-3 w-3 mr-1" /> Wait
            </Button>
            <Button size="sm" variant="outline" className="flex-1 text-xs h-7" onClick={() => addStep("PARK")}>
              <Plus className="h-3 w-3 mr-1" /> Park
            </Button>
          </div>

          {/* Templates */}
          <div className="flex gap-1">
            <Button size="sm" variant="ghost" className="text-xs h-7" onClick={loadTemplates}>
              <BookOpen className="h-3 w-3 mr-1" /> Load Template
            </Button>
          </div>
          {templates.length > 0 && (
            <div className="space-y-1 max-h-24 overflow-y-auto">
              {templates.map((t) => (
                <button
                  key={t.templateId}
                  className="w-full text-left text-xs px-2 py-1 bg-secondary/30 rounded hover:bg-secondary/50 text-foreground"
                  onClick={() => loadTemplate(t)}
                >
                  {t.name} ({t.steps?.length || 0} steps)
                </button>
              ))}
            </div>
          )}

          {/* Save as template */}
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={advSaveTemplate}
              onChange={(e) => setAdvSaveTemplate(e.target.checked)}
            />
            Save as Template
          </label>
          {advSaveTemplate && (
            <Input
              placeholder="Template name"
              value={advTemplateName}
              onChange={(e) => setAdvTemplateName(e.target.value)}
              className="h-8 text-sm"
            />
          )}

          <Button
            className="w-full gap-2"
            disabled={!robotId || !mapId || advSteps.length === 0}
            onClick={onSendAdvanced}
          >
            <Send className="h-4 w-4" /> Send Advanced Mission
          </Button>
        </TabsContent>
      </Tabs>
    </div>
  );
}
