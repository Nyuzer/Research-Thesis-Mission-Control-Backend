export async function fetchJSON<T>(
  url: string,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
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
  x: number;
  y: number;
  scheduledTime?: string;
  cron?: string;
}) {
  const body: any = {
    robotId: params.robotId,
    mapId: params.mapId,
    destination: { type: "Point", coordinates: [params.x, params.y, 0] },
  };
  if (params.scheduledTime) body.scheduledTime = params.scheduledTime;
  if (params.cron) body.cron = params.cron;
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
