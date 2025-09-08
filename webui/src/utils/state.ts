import { create } from "zustand";

type SelectionState = {
  selectedRobotId: string | null;
  selectedMapId: string | null;
  wsConnected: boolean;
  currentMissionId: string | null;
  robots: any[];
  destX: number | null;
  destY: number | null;
  mapMeta: {
    originX: number;
    originY: number;
    resolution: number;
    widthPx: number;
    heightPx: number;
    freeThresh: number;
    occupiedThresh: number;
    negate: number;
    imageUrl: string;
    freeValue?: number;
    occupiedValue?: number;
    unknownValue?: number;
    valueTolerance?: number;
  } | null;
  setSelectedRobotId: (id: string) => void;
  setSelectedMapId: (id: string) => void;
  setWsConnected: (v: boolean) => void;
  setCurrentMissionId: (id: string | null) => void;
  setRobots: (robots: any[]) => void;
  setDest: (x: number | null, y: number | null) => void;
  setMapMeta: (m: SelectionState["mapMeta"]) => void;
};

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedRobotId: null,
  selectedMapId: null,
  wsConnected: false,
  currentMissionId: null,
  robots: [],
  destX: null,
  destY: null,
  mapMeta: null,
  setSelectedRobotId: (id) => set({ selectedRobotId: id }),
  setSelectedMapId: (id) => set({ selectedMapId: id }),
  setWsConnected: (v) => set({ wsConnected: v }),
  setCurrentMissionId: (id) => set({ currentMissionId: id }),
  setRobots: (robots) => set({ robots }),
  setDest: (x, y) => set({ destX: x, destY: y }),
  setMapMeta: (m) => set({ mapMeta: m }),
}));
