import { getAuthHeaders, useAuthStore } from "./auth";

function parseErrorMessage(text: string, status: number): string {
  try {
    const json = JSON.parse(text);
    const detail = json.detail || json.message || json.error;
    if (typeof detail === "string") {
      if (detail.includes("Requires one of roles"))
        return "You don't have permission to perform this action";
      if (detail.includes("Not found"))
        return "The requested resource was not found";
      return detail;
    }
  } catch {}
  if (status === 403) return "You don't have permission to perform this action";
  if (status === 404) return "The requested resource was not found";
  if (status === 422) return "Invalid request data";
  if (status === 500) return "Server error. Please try again later";
  return text || `Request failed (${status})`;
}

export async function fetchJSON<T>(
  url: string,
  init?: RequestInit
): Promise<T> {
  const authHeaders = getAuthHeaders();
  const headers = new Headers(init?.headers);
  for (const [k, v] of Object.entries(authHeaders)) {
    if (!headers.has(k)) headers.set(k, v);
  }

  const res = await fetch(url, { ...init, headers });

  if (res.status === 401) {
    const refreshed = await useAuthStore.getState().refresh();
    if (refreshed) {
      const retryHeaders = new Headers(init?.headers);
      const newAuth = getAuthHeaders();
      for (const [k, v] of Object.entries(newAuth)) {
        retryHeaders.set(k, v);
      }
      const retry = await fetch(url, { ...init, headers: retryHeaders });
      if (!retry.ok) {
        const text = await retry.text();
        throw new Error(parseErrorMessage(text, retry.status));
      }
      return retry.json();
    }
    useAuthStore.getState().logout();
    throw new Error("Session expired");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorMessage(text, res.status));
  }
  return res.json();
}

export async function fetchRobots() {
  return fetchJSON<{ robots: any[]; count: number }>(`/api/robots`);
}

export async function fetchMaps() {
  return fetchJSON<{ maps: any[]; count: number }>(`/api/maps`);
}

export async function stopRobot(robotId: string) {
  return fetchJSON(`/api/robot/${encodeURIComponent(robotId)}/stop`, {
    method: "POST",
  });
}

export async function fetchRobotAutoPark(robotId: string) {
  return fetchJSON<{ robotId: string; enabled: boolean }>(
    `/api/robot/${encodeURIComponent(robotId)}/auto-park`
  );
}

export async function updateRobotAutoPark(robotId: string, enabled: boolean) {
  return fetchJSON<{ robotId: string; enabled: boolean }>(
    `/api/robot/${encodeURIComponent(robotId)}/auto-park`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }
  );
}

export async function sendMissionInstant(params: {
  robotId: string;
  mapId: string;
  x: number;
  y: number;
}) {
  const body = {
    robotId: params.robotId,
    mapId: params.mapId,
    destination: { type: "Point", coordinates: [params.x, params.y, 0] },
  };
  return fetchJSON(`/api/missions/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function sendMissionScheduled(params: {
  robotId: string;
  mapId: string;
  x?: number;
  y?: number;
  scheduledTime?: string;
  cron?: string;
  steps?: any[];
  name?: string;
}) {
  const body: any = {
    robotId: params.robotId,
    mapId: params.mapId,
  };
  if (params.x != null && params.y != null) {
    body.destination = { type: "Point", coordinates: [params.x, params.y, 0] };
  }
  if (params.scheduledTime) body.scheduledTime = params.scheduledTime;
  if (params.cron) body.cron = params.cron;
  if (params.steps) body.steps = params.steps;
  if (params.name) body.name = params.name;
  return fetchJSON(`/api/scheduled-missions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function fetchMapFiles(mapId: string) {
  return fetchJSON(`/api/maps/${encodeURIComponent(mapId)}/files`);
}

// Missions API
export async function fetchMissions() {
  return fetchJSON<{ missions: any[]; count: number }>(`/api/missions`);
}

export async function fetchScheduledMissions() {
  // Backend returns { scheduledMissions: [...], count }
  const res = await fetchJSON<{ scheduledMissions: any[]; count: number }>(
    `/api/scheduled-missions`
  );
  return { missions: res.scheduledMissions, count: res.count };
}

export async function deleteMission(missionId: string) {
  return fetchJSON(`/api/missions/${encodeURIComponent(missionId)}`, {
    method: "DELETE",
  });
}

export async function deleteScheduledMission(missionId: string) {
  return fetchJSON(`/api/scheduled-missions/${encodeURIComponent(missionId)}`, {
    method: "DELETE",
  });
}

// Maps API
export async function uploadMap(formData: FormData) {
  return fetchJSON(`/api/maps/upload`, {
    method: "POST",
    body: formData,
  });
}

export async function deleteMap(mapId: string) {
  return fetchJSON(`/api/maps/${encodeURIComponent(mapId)}`, {
    method: "DELETE",
  });
}

// Advanced Missions API
export async function sendAdvancedMission(data: {
  robotId: string;
  mapId: string;
  name?: string;
  steps: any[];
  saveAsTemplate?: boolean;
  templateName?: string;
}) {
  return fetchJSON(`/api/missions/advanced`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function fetchMissionTemplates() {
  return fetchJSON<any[]>(`/api/mission-templates`);
}

export async function deleteMissionTemplate(templateId: string) {
  return fetchJSON(`/api/mission-templates/${encodeURIComponent(templateId)}`, {
    method: "DELETE",
  });
}

// Zones API
export async function fetchZones(mapId: string) {
  return fetchJSON<any[]>(`/api/maps/${encodeURIComponent(mapId)}/zones`);
}

export async function createZone(
  mapId: string,
  data: { name: string; zoneType: string; polygon: number[][]; speedLimit?: number; color?: string; goalPoint?: number[]; isDefault?: boolean }
) {
  return fetchJSON(`/api/maps/${encodeURIComponent(mapId)}/zones`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateZone(
  mapId: string,
  zoneId: string,
  data: { goalPoint?: number[]; name?: string; isDefault?: boolean }
) {
  return fetchJSON(`/api/maps/${encodeURIComponent(mapId)}/zones/${encodeURIComponent(zoneId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteZone(mapId: string, zoneId: string) {
  return fetchJSON(`/api/maps/${encodeURIComponent(mapId)}/zones/${encodeURIComponent(zoneId)}`, {
    method: "DELETE",
  });
}

// Users API (admin only)
export async function fetchUsers() {
  return fetchJSON<any[]>(`/api/auth/users`);
}

export async function createUser(data: {
  email: string;
  username: string;
  password: string;
  role: string;
}) {
  return fetchJSON(`/api/auth/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateUser(
  userId: string,
  data: { email?: string; username?: string; password?: string; role?: string; is_active?: boolean }
) {
  return fetchJSON(`/api/auth/users/${encodeURIComponent(userId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteUser(userId: string) {
  return fetchJSON(`/api/auth/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}

// Robot API keys (admin only)
export interface RobotKey {
  id: string;
  name: string;
  robot_id: string;
  key_prefix: string;
  created_at: string;
}

export interface RobotKeyCreated extends RobotKey {
  api_key: string;
}

export async function fetchRobotKeys() {
  return fetchJSON<RobotKey[]>(`/api/auth/robot-keys`);
}

export async function createRobotKey(data: { name: string; robot_id: string }) {
  return fetchJSON<RobotKeyCreated>(`/api/auth/robot-keys`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteRobotKey(keyId: string) {
  return fetchJSON(`/api/auth/robot-keys/${encodeURIComponent(keyId)}`, {
    method: "DELETE",
  });
}
