import React, { useEffect, useRef, useState } from "react";
import L from "leaflet";
// @ts-ignore
import "proj4leaflet";
import proj4 from "proj4";

import { useSelectionStore } from "../utils/state";
import yaml from "js-yaml";
import { fetchMapFiles, fetchZones } from "../utils/api";
import { showToast } from "@/lib/toast";

// EPSG:25832 proj string
proj4.defs(
  "EPSG:25832",
  "+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs +type=crs"
);
const resolutions = Array.from({ length: 20 }, (_, i) => 1 / Math.pow(2, i));
const CRS_25832: any = new (L as any).Proj.CRS(
  "EPSG:25832",
  proj4.defs("EPSG:25832"),
  {
    origin: [0, 0],
    resolutions,
  }
);

/* ── Inline marker components (rendered inside the overlay <svg>) ── */

function RobotMarker({ cx, cy, label, isSelected }: { cx: number; cy: number; label: string; isSelected: boolean }) {
  const r = isSelected ? 8 : 6;
  return (
    <g>
      {/* Sonar pulse ring */}
      {isSelected && (
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#22d3ee" strokeWidth="2" opacity="0">
          <animate attributeName="r" from={String(r)} to={String(r + 18)} dur="1.8s" repeatCount="indefinite" />
          <animate attributeName="opacity" from="0.7" to="0" dur="1.8s" repeatCount="indefinite" />
        </circle>
      )}
      {/* Outer glow */}
      <circle cx={cx} cy={cy} r={r + 3} fill={isSelected ? "#22d3ee" : "#38bdf8"} opacity="0.2" />
      {/* Main dot */}
      <circle cx={cx} cy={cy} r={r} fill={isSelected ? "#22d3ee" : "#38bdf8"} stroke="#0f172a" strokeWidth="1.5" />
      {/* Inner highlight */}
      <circle cx={cx} cy={cy} r={r * 0.4} fill="white" opacity="0.7" />
      {/* Label */}
      <text
        x={cx}
        y={cy - r - 6}
        textAnchor="middle"
        fill="white"
        fontSize="10"
        fontFamily="Inter, sans-serif"
        fontWeight="600"
        paintOrder="stroke"
        stroke="#0f172a"
        strokeWidth="3"
        strokeLinejoin="round"
      >
        {label}
      </text>
    </g>
  );
}

function DestinationMarker({ cx, cy }: { cx: number; cy: number }) {
  const armLen = 10;
  const gap = 5;
  const r = 4;
  return (
    <g>
      {/* Pulsing outer ring */}
      <circle cx={cx} cy={cy} r={r + 2} fill="none" stroke="#f97316" strokeWidth="2" opacity="0">
        <animate attributeName="r" from={String(r + 2)} to={String(r + 14)} dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" from="0.6" to="0" dur="2s" repeatCount="indefinite" />
      </circle>
      {/* Crosshair arms */}
      <line x1={cx - armLen} y1={cy} x2={cx - gap} y2={cy} stroke="#f97316" strokeWidth="2" strokeLinecap="round" />
      <line x1={cx + gap} y1={cy} x2={cx + armLen} y2={cy} stroke="#f97316" strokeWidth="2" strokeLinecap="round" />
      <line x1={cx} y1={cy - armLen} x2={cx} y2={cy - gap} stroke="#f97316" strokeWidth="2" strokeLinecap="round" />
      <line x1={cx} y1={cy + gap} x2={cx} y2={cy + armLen} stroke="#f97316" strokeWidth="2" strokeLinecap="round" />
      {/* Outer ring */}
      <circle cx={cx} cy={cy} r={r + 2} fill="none" stroke="#f97316" strokeWidth="1.5" opacity="0.5" />
      {/* Center dot */}
      <circle cx={cx} cy={cy} r={r} fill="#f97316" stroke="#0f172a" strokeWidth="1.5" />
      <circle cx={cx} cy={cy} r={r * 0.4} fill="white" opacity="0.8" />
      {/* Label */}
      <text
        x={cx}
        y={cy - armLen - 4}
        textAnchor="middle"
        fill="#f97316"
        fontSize="9"
        fontFamily="Inter, sans-serif"
        fontWeight="600"
        paintOrder="stroke"
        stroke="#0f172a"
        strokeWidth="3"
        strokeLinejoin="round"
      >
        DEST
      </text>
    </g>
  );
}

/* ── Zone polygon overlay ── */
function ZonePolygon({
  polygon,
  zoneType,
  name,
  speedLimit,
  color,
  toPixel,
}: {
  polygon: number[][];
  zoneType: string;
  name: string;
  speedLimit?: number | null;
  color?: string | null;
  toPixel: (wx: number, wy: number) => { cx: number; cy: number };
}) {
  const points = polygon.map(([x, y]) => toPixel(x, y));
  if (points.some((p) => !isFinite(p.cx) || !isFinite(p.cy))) return null;
  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.cx} ${p.cy}`).join(" ") + " Z";
  const fill = color || (zoneType === "parking" ? "rgba(59,130,246,0.25)" : "rgba(245,158,11,0.25)");
  const stroke = zoneType === "parking" ? "#3b82f6" : "#f59e0b";
  // Centroid for label
  const cx = points.reduce((s, p) => s + p.cx, 0) / points.length;
  const cy = points.reduce((s, p) => s + p.cy, 0) / points.length;
  const label = zoneType === "parking" ? `P: ${name}` : `${speedLimit ?? "?"} m/s`;

  return (
    <g>
      <path d={pathD} fill={fill} stroke={stroke} strokeWidth="2" strokeDasharray={zoneType === "speed_limit" ? "6 3" : "none"} />
      <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" fill={stroke} fontSize="10" fontWeight="700" paintOrder="stroke" stroke="#0f172a" strokeWidth="2.5" strokeLinejoin="round" fontFamily="Inter, sans-serif">
        {label}
      </text>
    </g>
  );
}

/* ── Dashed line between robot and destination ── */
function ConnectionLine({ x1, y1, x2, y2 }: { x1: number; y1: number; x2: number; y2: number }) {
  return (
    <line
      x1={x1} y1={y1} x2={x2} y2={y2}
      stroke="#f97316"
      strokeWidth="1"
      strokeDasharray="4 3"
      opacity="0.5"
    />
  );
}

export default function MapView() {
  const mapDivRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const robotLayerRef = useRef<any>(null);
  const destMarkerRef = useRef<any>(null);
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);
  const [imgSrc, setImgSrc] = useState<string>("");
  const overlayContainerRef = useRef<HTMLDivElement | null>(null);
  const offscreenCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const selectedMapId = useSelectionStore((s) => s.selectedMapId);
  const setMapMeta = useSelectionStore((s) => s.setMapMeta);
  const setDest = useSelectionStore((s) => s.setDest);
  const robots = useSelectionStore((s) => s.robots);
  const dest = useSelectionStore((s) => ({ x: s.destX, y: s.destY }));
  const selectedRobotId = useSelectionStore((s) => s.selectedRobotId);
  const zones = useSelectionStore((s) => s.zones);
  const showZones = useSelectionStore((s) => s.showZones);

  // Initialize Leaflet map once
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return;
    const map = L.map(mapDivRef.current, {
      crs: CRS_25832,
      center: [0, 0],
      zoom: 1,
      zoomControl: false,
      dragging: false,
      scrollWheelZoom: false,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
      touchZoom: false,
    });
    mapRef.current = map;
    robotLayerRef.current = L.layerGroup().addTo(map);
    map.on("click", (e: any) => {
      const { lat, lng } = e.latlng;
      setDest(lng, lat);
      if (destMarkerRef.current) destMarkerRef.current.remove();
      destMarkerRef.current = L.circleMarker([lat, lng], {
        radius: 5,
        color: "blue",
      }).addTo(map);
    });
    return () => {
      try {
        map.remove();
      } catch {}
      mapRef.current = null;
      robotLayerRef.current = null;
      destMarkerRef.current = null;
    };
  }, []);

  // Load selected map and overlay image
  useEffect(() => {
    const load = async () => {
      if (!selectedMapId || !mapRef.current) return;
      try {
        const info: any = await fetchMapFiles(selectedMapId);
        const yamlContent = info?.files?.yaml?.content as string;
        const imageUrl = info?.files?.image?.downloadUrl as string;
        const config: any = yaml.load(yamlContent || "") || {};
        const resolution = Number(config.resolution || 0.05);
        const originArr = Array.isArray(config.origin)
          ? config.origin
          : [0, 0, 0];
        const originX = Number(originArr[0] || 0);
        const originY = Number(originArr[1] || 0);
        const freeThresh = Number(config.free_thresh ?? 0.196);
        const occupiedThresh = Number(config.occupied_thresh ?? 0.65);
        const freeValue =
          config.free_value !== undefined
            ? Number(config.free_value)
            : undefined;
        const occupiedValue =
          config.occupied_value !== undefined
            ? Number(config.occupied_value)
            : undefined;
        const unknownValue =
          config.unknown_value !== undefined
            ? Number(config.unknown_value)
            : undefined;
        const valueTolerance =
          config.value_tolerance !== undefined
            ? Number(config.value_tolerance)
            : 10;
        const negate = Number(config.negate ?? 0);

        const absUrl = imageUrl.startsWith("http")
          ? imageUrl
          : `${window.location.origin}${imageUrl}`;

        const img = new Image();
        img.onload = () => {
          const widthPx = img.width;
          const heightPx = img.height;
          setImgSize({ w: widthPx, h: heightPx });
          setMapMeta({
            originX,
            originY,
            resolution,
            widthPx,
            heightPx,
            freeThresh,
            occupiedThresh,
            negate,
            imageUrl: absUrl,
            freeValue,
            occupiedValue,
            unknownValue,
            valueTolerance,
          });
          setImgSrc(absUrl);
          if (!offscreenCanvasRef.current) {
            offscreenCanvasRef.current = document.createElement("canvas");
          }
          const oc = offscreenCanvasRef.current;
          oc.width = widthPx;
          oc.height = heightPx;
          const octx = oc.getContext("2d");
          if (octx) {
            octx.clearRect(0, 0, widthPx, heightPx);
            octx.drawImage(img, 0, 0);
          }

          const minX = originX;
          const minY = originY;
          const maxX = originX + widthPx * resolution;
          const maxY = originY + heightPx * resolution;
          const bounds = L.latLngBounds(
            L.latLng(minY, minX) as any,
            L.latLng(maxY, maxX) as any
          );
          mapRef.current.fitBounds(bounds as any, { padding: [20, 20] as any });
        };
        img.src = absUrl;
        // Load zones for this map
        try {
          const z = await fetchZones(selectedMapId);
          useSelectionStore.getState().setZones(z || []);
        } catch {
          useSelectionStore.getState().setZones([]);
        }
      } catch (e) {
        console.warn("Failed to load map files", e);
      }
    };
    load();
  }, [selectedMapId]);

  // Render robots on LayerGroup
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !robotLayerRef.current) return;
    robotLayerRef.current.clearLayers();
    robots.forEach((r) => {
      if (r.position25832) {
        const [x, y] = r.position25832;
        const marker = L.circleMarker([y, x], { radius: 5, color: "red" });
        marker.bindTooltip(`${r.name || r.robotId}`);
        marker.addTo(robotLayerRef.current);
      }
    });
  }, [robots]);

  const onImageClick = (ev: React.MouseEvent) => {
    const imgEl = ev.currentTarget as HTMLImageElement;
    if (!imgSize) return;
    const rect = imgEl.getBoundingClientRect();
    const clickX = ev.clientX - rect.left;
    const clickY = ev.clientY - rect.top;
    const scaleX = imgSize.w / rect.width;
    const scaleY = imgSize.h / rect.height;
    const px = clickX * scaleX;
    const pyFromTop = clickY * scaleY;
    const meta = useSelectionStore.getState().mapMeta;
    if (!meta) return;
    const oc = offscreenCanvasRef.current;
    const octx = oc?.getContext("2d");
    if (oc && octx) {
      const ix = Math.floor(px);
      const iy = Math.floor(pyFromTop);
      if (ix >= 0 && iy >= 0 && ix < oc.width && iy < oc.height) {
        const d = octx.getImageData(ix, iy, 1, 1).data;
        const r = d[0],
          g = d[1],
          b = d[2];
        let byteVal = Math.round(0.299 * r + 0.587 * g + 0.114 * b);
        if (meta.negate === 1) byteVal = 255 - byteVal;
        const freeV = meta.freeValue ?? 0;
        const occV = meta.occupiedValue ?? 100;
        const unkV = meta.unknownValue ?? 255;
        const tol = meta.valueTolerance ?? 10;
        const near = (a: number, b: number) => Math.abs(a - b) <= tol;
        const isFree = near(byteVal, freeV);
        const isOccupied = near(byteVal, occV);
        const isUnknown = near(byteVal, unkV);
        if (!isFree || isOccupied || isUnknown) {
          showToast("Selected point is not free (byte-based)", "warning");
          return;
        }
      }
    }
    const pyFromBottom = imgSize.h - pyFromTop;
    const worldX = meta.originX + px * meta.resolution;
    const worldY = meta.originY + pyFromBottom * meta.resolution;
    setDest(worldX, worldY);
  };

  // Robot outside selected map warning
  const lastWarnRef = useRef<string | null>(null);
  useEffect(() => {
    const meta = useSelectionStore.getState().mapMeta;
    if (!meta || !selectedRobotId) return;
    const robot = robots.find((r: any) => r.robotId === selectedRobotId);
    if (!robot || !Array.isArray(robot.position25832)) return;
    const [rx, ry] = robot.position25832;
    const minX = meta.originX;
    const minY = meta.originY;
    const maxX = meta.originX + meta.widthPx * meta.resolution;
    const maxY = meta.originY + meta.heightPx * meta.resolution;
    const inside = rx >= minX && rx <= maxX && ry >= minY && ry <= maxY;
    const key = `${selectedRobotId}:${meta.imageUrl}`;
    if (!inside && lastWarnRef.current !== key) {
      lastWarnRef.current = key;
      showToast("Robot not inside selected map", "warning");
    }
  }, [robots, selectedRobotId]);

  return (
    <div className="relative h-full w-full">
      <div
        ref={mapDivRef}
        className="absolute inset-0 z-0 pointer-events-none bg-transparent"
      />
      <div
        ref={overlayContainerRef}
        className="absolute inset-0 z-[1] flex justify-center items-start overflow-auto bg-card"
      >
        {imgSrc && (
          <img
            src={imgSrc}
            alt="map"
            className="max-w-full h-auto cursor-crosshair block mx-auto"
            onClick={onImageClick}
          />
        )}
        {imgSize &&
          (() => {
            const meta = useSelectionStore.getState().mapMeta;
            const imgEl = document.querySelector(
              'img[alt="map"]'
            ) as HTMLImageElement | null;
            const contEl = overlayContainerRef.current;
            if (!meta || !imgEl || !contEl) return null;
            const imgRect = imgEl.getBoundingClientRect();
            const contRect = contEl.getBoundingClientRect();
            const left = imgRect.left - contRect.left;
            const top = imgRect.top - contRect.top;
            const width = imgRect.width;
            const height = imgRect.height;
            const scaleX = imgSize.w / width;
            const scaleY = imgSize.h / height;

            const toPixel = (wx: number, wy: number) => {
              const px = (wx - meta.originX) / meta.resolution;
              const pyFromBottom = (wy - meta.originY) / meta.resolution;
              const py = imgSize.h - pyFromBottom;
              const cx = px / scaleX;
              const cy = py / scaleY;
              return { cx, cy };
            };

            // Pre-compute selected robot position for connection line
            const selectedRobot = robots.find((r: any) => r.robotId === selectedRobotId);
            let selectedRobotPixel: { cx: number; cy: number } | null = null;
            if (selectedRobot && Array.isArray(selectedRobot.position25832)) {
              const [wx, wy] = selectedRobot.position25832;
              const p = toPixel(wx, wy);
              if (isFinite(p.cx) && isFinite(p.cy)) selectedRobotPixel = p;
            }

            let destPixel: { cx: number; cy: number } | null = null;
            if (dest.x != null && dest.y != null) {
              const p = toPixel(dest.x!, dest.y!);
              if (isFinite(p.cx) && isFinite(p.cy)) destPixel = p;
            }

            return (
              <div
                style={{
                  position: "absolute",
                  left,
                  top,
                  width,
                  height,
                  pointerEvents: "none",
                }}
              >
                <svg width="100%" height="100%" style={{ display: "block", overflow: "visible" }}>
                  {/* Zone polygons */}
                  {showZones && zones.map((z: any) => (
                    <ZonePolygon
                      key={z.zoneId}
                      polygon={z.polygon}
                      zoneType={z.zoneType}
                      name={z.name}
                      speedLimit={z.speedLimit}
                      color={z.color}
                      toPixel={toPixel}
                    />
                  ))}
                  {/* Connection line from selected robot to destination */}
                  {selectedRobotPixel && destPixel && (
                    <ConnectionLine
                      x1={selectedRobotPixel.cx}
                      y1={selectedRobotPixel.cy}
                      x2={destPixel.cx}
                      y2={destPixel.cy}
                    />
                  )}
                  {/* Robot markers */}
                  {robots &&
                    robots.map((r: any) => {
                      if (!Array.isArray(r.position25832)) return null;
                      const [wx, wy] = r.position25832;
                      const { cx, cy } = toPixel(wx, wy);
                      if (!isFinite(cx) || !isFinite(cy)) return null;
                      return (
                        <RobotMarker
                          key={r.robotId}
                          cx={cx}
                          cy={cy}
                          label={r.name || r.robotId}
                          isSelected={r.robotId === selectedRobotId}
                        />
                      );
                    })}
                  {/* Destination marker */}
                  {destPixel && (
                    <DestinationMarker cx={destPixel.cx} cy={destPixel.cy} />
                  )}
                </svg>
              </div>
            );
          })()}
      </div>
    </div>
  );
}
