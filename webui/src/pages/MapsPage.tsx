import { useQuery } from "@tanstack/react-query";
import { fetchMaps, uploadMap, deleteMap } from "../utils/api";
import { useRef, useState, useEffect, useCallback, useMemo } from "react";
import { removeLocalTemplatesForMap, cleanupOrphanTemplates } from "@/utils/localTemplates";
import ConfirmDeleteDialog from "@/components/ConfirmDeleteDialog";
import { showToast } from "@/lib/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { format } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import DataTablePagination from "@/components/DataTablePagination";
import { Trash2, Upload, X, Search, Filter } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/utils/auth";

/* Mobile card for a single map row */
function MapCard({
  m,
  imgMeta,
  onImgLoad,
  onImageClick,
  onDelete,
  canDelete,
}: {
  m: any;
  imgMeta: Record<string, { w: number; h: number }>;
  onImgLoad: (mapId: string, ev: React.SyntheticEvent<HTMLImageElement>) => void;
  onImageClick: (src: string, name: string) => void;
  onDelete: () => void;
  canDelete: boolean;
}) {
  return (
    <div className="border border-border rounded-lg p-3 bg-card space-y-2">
      <div className="flex gap-3">
        <img
          src={`/api/maps/${m.mapId}/image`}
          alt={m.name}
          className="w-16 h-16 object-cover rounded border border-border cursor-pointer hover:opacity-80 transition-opacity shrink-0"
          onLoad={(e) => onImgLoad(m.mapId, e)}
          onClick={() => onImageClick(`/api/maps/${m.mapId}/image`, m.name || m.mapId)}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium truncate">{m.name || m.mapId}</span>
            {canDelete && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0"
                onClick={onDelete}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs mt-1">
            <span className="text-muted-foreground">Resolution</span>
            <span className="font-mono">{m.resolution}</span>
            <span className="text-muted-foreground">Size</span>
            <span className="font-mono">
              {imgMeta[m.mapId]?.w
                ? `${imgMeta[m.mapId].w}\u00d7${imgMeta[m.mapId].h}`
                : "\u2014"}
            </span>
            <span className="text-muted-foreground">Origin</span>
            <span className="font-mono truncate">
              {Array.isArray(m.origin)
                ? `${m.origin[0]}, ${m.origin[1]}`
                : "\u2014"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MapsPage() {
  const userRole = useAuthStore((s) => s.user?.role);
  const canEdit = userRole !== "viewer";
  const { data, refetch } = useQuery({
    queryKey: ["maps"],
    queryFn: fetchMaps,
  });
  const yamlRef = useRef<HTMLInputElement | null>(null);
  const imgRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState(10);
  const [imgMeta, setImgMeta] = useState<
    Record<string, { w: number; h: number }>
  >({});
  const [lightbox, setLightbox] = useState<{ src: string; name: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [dateFrom, setDateFrom] = useState<Date | undefined>(undefined);
  const [dateTo, setDateTo] = useState<Date | undefined>(undefined);

  const hasFilters = Boolean(q || dateFrom || dateTo);
  const clearFilters = () => { setQ(""); setDateFrom(undefined); setDateTo(undefined); setPage(0); };

  const filteredMaps = useMemo(() => {
    const all = data?.maps || [];
    const from = dateFrom ? dateFrom.getTime() : 0;
    const to = dateTo ? dateTo.getTime() + 86400000 - 1 : Infinity;
    return all.filter((m: any) => {
      if (q) {
        const text = `${m.mapId} ${m.name || ""}`.toLowerCase();
        if (!text.includes(q.toLowerCase())) return false;
      }
      if (from || to < Infinity) {
        const t = m.uploadTime ? new Date(m.uploadTime).getTime() : 0;
        if (t && (t < from || t > to)) return false;
      }
      return true;
    });
  }, [data, q, dateFrom, dateTo]);

  // Cleanup orphaned localStorage templates for deleted maps
  useEffect(() => {
    if (data?.maps) {
      cleanupOrphanTemplates(data.maps.map((m: any) => m.mapId));
    }
  }, [data]);

  const handleImgLoad = (
    mapId: string,
    ev: React.SyntheticEvent<HTMLImageElement>
  ) => {
    const img = ev.currentTarget;
    setImgMeta((prev) => ({
      ...prev,
      [mapId]: { w: img.naturalWidth, h: img.naturalHeight },
    }));
  };

  const onUpload = async () => {
    const yamlFile = yamlRef.current?.files?.[0];
    const imgFile = imgRef.current?.files?.[0];
    if (!yamlFile || !imgFile) {
      showToast("Select YAML and PNG/PGM", "warning");
      return;
    }
    if (!yamlFile.name.endsWith(".yaml")) {
      showToast("YAML must have .yaml extension", "warning");
      return;
    }
    if (!(imgFile.name.endsWith(".png") || imgFile.name.endsWith(".pgm"))) {
      showToast("Image must be .png or .pgm", "warning");
      return;
    }
    const form = new FormData();
    form.append("map_yaml", yamlFile);
    form.append("map_image", imgFile);
    try {
      setUploading(true);
      await uploadMap(form);
      showToast("Map uploaded", "success");
      yamlRef.current!.value = "";
      imgRef.current!.value = "";
      refetch();
    } catch (e: any) {
      showToast(e?.message || "Upload failed", "error");
    } finally {
      setUploading(false);
    }
  };

  const onDeleteConfirmed = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await deleteMap(deleteTarget);
      removeLocalTemplatesForMap(deleteTarget);
      showToast("Map deleted", "success");
      refetch();
    } catch (e: any) {
      showToast(e?.message || "Delete failed", "error");
    } finally {
      setDeleteTarget(null);
    }
  }, [deleteTarget, refetch]);

  // Close lightbox on Escape
  const closeLightbox = useCallback(() => setLightbox(null), []);
  useEffect(() => {
    if (!lightbox) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeLightbox();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, closeLightbox]);

  const openLightbox = (src: string, name: string) => setLightbox({ src, name });

  return (
    <div className="p-3 sm:p-4 max-w-7xl mx-auto overflow-auto h-full">
      <h2 className="text-lg font-semibold mb-3">Maps Manager</h2>

      {canEdit && (
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 mb-4">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => yamlRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" />
            Choose YAML
          </Button>
          <input
            ref={yamlRef}
            type="file"
            accept=".yaml"
            className="hidden"
          />
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => imgRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" />
            Choose PNG/PGM
          </Button>
          <input
            ref={imgRef}
            type="file"
            accept=".png,.pgm"
            className="hidden"
          />
          <Button size="sm" onClick={onUpload} disabled={uploading}>
            {uploading ? "Uploading..." : "Upload"}
          </Button>
        </div>
      )}

      {/* Filters */}
      <div className="grid grid-cols-2 sm:flex sm:flex-wrap sm:items-center gap-2 mb-3">
        <div className="relative col-span-2">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search name or ID..."
            value={q}
            onChange={(e) => { setQ(e.target.value); setPage(0); }}
            className="pl-7 h-8 w-full sm:w-[200px] text-xs"
          />
        </div>
        <Popover>
          <PopoverTrigger className={cn("inline-flex items-center h-8 w-full sm:w-[120px] text-xs font-normal px-3 border rounded-md bg-background shadow-xs hover:bg-accent dark:border-input dark:bg-input/30 dark:hover:bg-input/50", !dateFrom && "text-muted-foreground")}>
            {dateFrom ? format(dateFrom, "dd.MM.yyyy") : "From"}
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar mode="single" selected={dateFrom} onSelect={(d) => { setDateFrom(d); setPage(0); }} />
          </PopoverContent>
        </Popover>
        <Popover>
          <PopoverTrigger className={cn("inline-flex items-center h-8 w-full sm:w-[120px] text-xs font-normal px-3 border rounded-md bg-background shadow-xs hover:bg-accent dark:border-input dark:bg-input/30 dark:hover:bg-input/50", !dateTo && "text-muted-foreground")}>
            {dateTo ? format(dateTo, "dd.MM.yyyy") : "To"}
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar mode="single" selected={dateTo} onSelect={(d) => { setDateTo(d); setPage(0); }} />
          </PopoverContent>
        </Popover>
        <div className="col-span-2 sm:col-span-1 flex items-center justify-between sm:justify-start gap-2">
          {hasFilters && (
            <Button variant="ghost" size="sm" className="text-xs h-8 gap-1 text-muted-foreground" onClick={clearFilters}>
              <X className="h-3 w-3" /> Clear
            </Button>
          )}
          <span className="text-xs text-muted-foreground sm:ml-auto">{filteredMaps.length} maps</span>
        </div>
      </div>

      {/* Mobile: cards */}
      <div className="space-y-2 md:hidden">
        {filteredMaps
          .slice(page * rows, page * rows + rows)
          .map((m: any) => (
            <MapCard
              key={m.mapId}
              m={m}
              imgMeta={imgMeta}
              onImgLoad={handleImgLoad}
              onImageClick={openLightbox}
              onDelete={() => setDeleteTarget(m.mapId)}
              canDelete={canEdit}
            />
          ))}
      </div>

      {/* Desktop: table */}
      <div className="hidden md:block rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="text-xs">Preview</TableHead>
              <TableHead className="text-xs">Map ID</TableHead>
              <TableHead className="text-xs">Name</TableHead>
              <TableHead className="text-xs">Resolution</TableHead>
              <TableHead className="text-xs">Size (px)</TableHead>
              <TableHead className="text-xs">Origin</TableHead>
              <TableHead className="text-xs">Uploaded</TableHead>
              {canEdit && <TableHead className="text-xs text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredMaps
              .slice(page * rows, page * rows + rows)
              .map((m: any) => (
                <TableRow key={m.mapId}>
                  <TableCell>
                    <img
                      src={`/api/maps/${m.mapId}/image`}
                      alt={m.name}
                      className="w-20 h-auto rounded border border-border cursor-pointer hover:opacity-80 transition-opacity"
                      onLoad={(e) => handleImgLoad(m.mapId, e)}
                      onClick={() => openLightbox(`/api/maps/${m.mapId}/image`, m.name || m.mapId)}
                    />
                  </TableCell>
                  <TableCell className="text-xs font-mono">
                    {m.mapId}
                  </TableCell>
                  <TableCell className="text-xs">{m.name}</TableCell>
                  <TableCell className="text-xs font-mono">
                    {m.resolution}
                  </TableCell>
                  <TableCell className="text-xs font-mono">
                    {imgMeta[m.mapId]?.w
                      ? `${imgMeta[m.mapId].w} \u00d7 ${imgMeta[m.mapId].h}`
                      : "\u2014"}
                  </TableCell>
                  <TableCell className="text-xs font-mono">
                    {Array.isArray(m.origin)
                      ? `${m.origin[0]}, ${m.origin[1]}, ${m.origin[2] ?? 0}`
                      : "\u2014"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {m.uploadTime}
                  </TableCell>
                  {canEdit && (
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setDeleteTarget(m.mapId)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>
      <DataTablePagination
        count={filteredMaps.length}
        page={page}
        rowsPerPage={rows}
        onPageChange={setPage}
        onRowsPerPageChange={(r) => {
          setRows(r);
          setPage(0);
        }}
      />

      <ConfirmDeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        onConfirm={onDeleteConfirmed}
        title="Delete map?"
        description="This will permanently delete this map and its files. This action cannot be undone."
      />

      {/* Lightbox overlay */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
          onClick={closeLightbox}
        >
          <div
            className="relative max-w-[90vw] max-h-[90vh]"
            onClick={(e) => e.stopPropagation()}
          >
            <Button
              variant="ghost"
              size="icon"
              className="absolute -top-10 right-0 text-white hover:text-white/80 hover:bg-white/10"
              onClick={closeLightbox}
            >
              <X className="h-5 w-5" />
            </Button>
            <p className="absolute -top-10 left-0 text-sm text-white/70 truncate max-w-[70vw]">
              {lightbox.name}
            </p>
            <img
              src={lightbox.src}
              alt={lightbox.name}
              className="max-w-[90vw] max-h-[85vh] object-contain rounded-lg border border-border"
            />
          </div>
        </div>
      )}
    </div>
  );
}
