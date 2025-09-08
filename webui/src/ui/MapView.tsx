import React, { useEffect, useRef, useState } from "react";
import L from "leaflet";
// @ts-ignore
import "proj4leaflet";
import proj4 from "proj4";
import { Box } from "@mui/material";

import { useSelectionStore } from "../utils/state";
import yaml from "js-yaml";
import { fetchMapFiles } from "../utils/api";
import { useSnackbar } from "notistack";
import RobotSvg from "../robot-ai.svg";
import GoalSvg from "../goal.svg";

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
  const { enqueueSnackbar } = useSnackbar();

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
        // Optional byte-based config
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
          // Prepare offscreen canvas for pixel sampling
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
      } catch (e) {
        // eslint-disable-next-line no-console
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
    // compute world coords from image pixel
    const imgEl = ev.currentTarget as HTMLImageElement;
    if (!imgSize) return;
    const rect = imgEl.getBoundingClientRect();
    const clickX = ev.clientX - rect.left;
    const clickY = ev.clientY - rect.top;
    const scaleX = imgSize.w / rect.width;
    const scaleY = imgSize.h / rect.height;
    const px = clickX * scaleX;
    const pyFromTop = clickY * scaleY;
    // mapMeta is stored in store
    const meta = useSelectionStore.getState().mapMeta;
    if (!meta) return;
    // Free-area validation using offscreen canvas and byte values
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
        // Default mapping if not provided in YAML
        const freeV = meta.freeValue ?? 0;
        const occV = meta.occupiedValue ?? 100;
        const unkV = meta.unknownValue ?? 255;
        const tol = meta.valueTolerance ?? 10;
        const near = (a: number, b: number) => Math.abs(a - b) <= tol;
        const isFree = near(byteVal, freeV);
        const isOccupied = near(byteVal, occV);
        const isUnknown = near(byteVal, unkV);
        if (!isFree || isOccupied || isUnknown) {
          enqueueSnackbar("Selected point is not free (byte-based)", {
            variant: "warning",
          });
          return;
        }
      }
    }
    const pyFromBottom = imgSize.h - pyFromTop;
    const worldX = meta.originX + px * meta.resolution;
    const worldY = meta.originY + pyFromBottom * meta.resolution;
    setDest(worldX, worldY);
    // draw destination as a small blue circle on overlay
    // we will reuse robot layer later for Leaflet markers if needed
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
      enqueueSnackbar("Robot not inside selected map", { variant: "warning" });
    }
  }, [robots, selectedRobotId]);

  return (
    <Box position="relative" height="100%" width="100%">
      <div
        ref={mapDivRef}
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 0,
          pointerEvents: "none",
          background: "transparent",
        }}
      />
      <Box
        sx={{
          position: "absolute",
          inset: 0,
          zIndex: 1,
          display: "flex",
          justifyContent: "center",
          alignItems: "flex-start",
          overflow: "auto",
          bgcolor: "background.paper",
        }}
        ref={overlayContainerRef}
      >
        {imgSrc && (
          <img
            src={imgSrc}
            alt="map"
            style={{
              maxWidth: "100%",
              height: "auto",
              cursor: "crosshair",
              display: "block",
              margin: "0 auto",
            }}
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
                <svg width="100%" height="100%" style={{ display: "block" }}>
                  {robots &&
                    robots.map((r: any) => {
                      if (!Array.isArray(r.position25832)) return null;
                      const [wx, wy] = r.position25832;
                      const { cx, cy } = toPixel(wx, wy);
                      if (!isFinite(cx) || !isFinite(cy)) return null;
                      const size = 20;
                      return (
                        <image
                          key={r.robotId}
                          href={RobotSvg}
                          x={cx - size / 2}
                          y={cy - size / 2}
                          width={size}
                          height={size}
                        />
                      );
                    })}
                  {dest.x != null &&
                    dest.y != null &&
                    (() => {
                      const { cx, cy } = toPixel(dest.x!, dest.y!);
                      if (!isFinite(cx) || !isFinite(cy)) return null;
                      return (
                        <image
                          href={GoalSvg}
                          x={cx - 18 / 2}
                          y={cy - 18 / 2}
                          width={18}
                          height={18}
                        />
                      );
                    })()}
                </svg>
              </div>
            );
          })()}
      </Box>
    </Box>
  );
}
