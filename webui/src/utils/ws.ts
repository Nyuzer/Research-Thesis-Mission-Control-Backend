import ReconnectingWebSocket from "reconnecting-websocket";
import { useSelectionStore } from "./state";

let rws: ReconnectingWebSocket | null = null;

export function startWS() {
  if (rws) return;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const envUrl = (import.meta as any).env?.VITE_WS_URL as string | undefined;
  let url = envUrl;
  if (!url) {
    const host = window.location.hostname;
    const port = window.location.port;
    if (port === "5173") {
      url = `${proto}://${host}:8000/ws`;
    } else {
      url = `${proto}://${location.host}/ws`;
    }
  }
  rws = new ReconnectingWebSocket(url);

  rws.addEventListener("open", () => {
    useSelectionStore.getState().setWsConnected(true);
  });
  rws.addEventListener("close", () => {
    useSelectionStore.getState().setWsConnected(false);
  });
  rws.addEventListener("message", (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data?.type === "robot_snapshot" && Array.isArray(data.robots)) {
        useSelectionStore.getState().setRobots(data.robots);
        const selId = useSelectionStore.getState().selectedRobotId;
        if (selId) {
          const r = data.robots.find((rr: any) => rr.robotId === selId);
          useSelectionStore
            .getState()
            .setCurrentMissionId(r?.currentMissionId || null);
        }
      }
    } catch {}
  });
}

export function stopWS() {
  if (rws) {
    rws.close();
    rws = null;
  }
}
