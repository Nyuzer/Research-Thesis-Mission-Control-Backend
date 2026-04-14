const LOCAL_TPL_PREFIX = "mission_templates:";

export function getLocalTemplates(mapId: string): any[] {
  try {
    const raw = localStorage.getItem(LOCAL_TPL_PREFIX + mapId);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function saveLocalTemplate(mapId: string, name: string, steps: any[]) {
  try {
    const existing = getLocalTemplates(mapId);
    existing.push({ name, steps, savedAt: new Date().toISOString() });
    localStorage.setItem(LOCAL_TPL_PREFIX + mapId, JSON.stringify(existing));
  } catch {}
}

export function deleteLocalTemplate(mapId: string, index: number) {
  try {
    const existing = getLocalTemplates(mapId);
    existing.splice(index, 1);
    if (existing.length === 0) {
      localStorage.removeItem(LOCAL_TPL_PREFIX + mapId);
    } else {
      localStorage.setItem(LOCAL_TPL_PREFIX + mapId, JSON.stringify(existing));
    }
  } catch {}
}

export function removeLocalTemplatesForMap(mapId: string) {
  try {
    localStorage.removeItem(LOCAL_TPL_PREFIX + mapId);
  } catch {}
}

export function cleanupOrphanTemplates(existingMapIds: string[]) {
  try {
    const mapIdSet = new Set(existingMapIds);
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(LOCAL_TPL_PREFIX)) {
        const mapId = key.slice(LOCAL_TPL_PREFIX.length);
        if (!mapIdSet.has(mapId)) {
          keysToRemove.push(key);
        }
      }
    }
    for (const key of keysToRemove) {
      localStorage.removeItem(key);
    }
  } catch {}
}
