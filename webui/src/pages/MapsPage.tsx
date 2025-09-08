import {
  Box,
  Typography,
  Stack,
  Button,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TablePagination,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { fetchMaps, uploadMap, deleteMap } from "../utils/api";
import { useRef, useState } from "react";
import { useSnackbar } from "notistack";

export default function MapsPage() {
  const { data, refetch } = useQuery({
    queryKey: ["maps"],
    queryFn: fetchMaps,
  });
  const yamlRef = useRef<HTMLInputElement | null>(null);
  const imgRef = useRef<HTMLInputElement | null>(null);
  const { enqueueSnackbar } = useSnackbar();
  const [uploading, setUploading] = useState(false);
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState(10);
  const [imgMeta, setImgMeta] = useState<
    Record<string, { w: number; h: number }>
  >({});

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
      enqueueSnackbar("Select YAML and PNG/PGM", { variant: "warning" });
      return;
    }
    if (!yamlFile.name.endsWith(".yaml")) {
      enqueueSnackbar("YAML must have .yaml extension", { variant: "warning" });
      return;
    }
    if (!(imgFile.name.endsWith(".png") || imgFile.name.endsWith(".pgm"))) {
      enqueueSnackbar("Image must be .png or .pgm", { variant: "warning" });
      return;
    }
    const form = new FormData();
    form.append("map_yaml", yamlFile);
    form.append("map_image", imgFile);
    try {
      setUploading(true);
      await uploadMap(form);
      enqueueSnackbar("Map uploaded", { variant: "success" });
      yamlRef.current!.value = "";
      imgRef.current!.value = "";
      refetch();
    } catch (e: any) {
      enqueueSnackbar(e?.message || "Upload failed", { variant: "error" });
    } finally {
      setUploading(false);
    }
  };

  const onDelete = async (mapId: string) => {
    try {
      await deleteMap(mapId);
      enqueueSnackbar("Map deleted", { variant: "success" });
      refetch();
    } catch (e: any) {
      enqueueSnackbar(e?.message || "Delete failed", { variant: "error" });
    }
  };

  return (
    <Box p={2}>
      <Typography variant="h5" mb={2}>
        Maps Manager
      </Typography>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        mb={2}
        alignItems="center"
      >
        <Button variant="outlined" onClick={() => yamlRef.current?.click()}>
          Choose YAML
        </Button>
        <input
          ref={yamlRef}
          type="file"
          accept=".yaml"
          style={{ display: "none" }}
        />
        <Button variant="outlined" onClick={() => imgRef.current?.click()}>
          Choose PNG/PGM
        </Button>
        <input
          ref={imgRef}
          type="file"
          accept=".png,.pgm"
          style={{ display: "none" }}
        />
        <Button variant="contained" onClick={onUpload} disabled={uploading}>
          Upload
        </Button>
      </Stack>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Preview</TableCell>
            <TableCell>Map ID</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Resolution</TableCell>
            <TableCell>Size (px)</TableCell>
            <TableCell>Origin</TableCell>
            <TableCell>Uploaded</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data?.maps?.slice(page * rows, page * rows + rows).map((m: any) => (
            <TableRow key={m.mapId} hover>
              <TableCell>
                <img
                  src={`/api/maps/${m.mapId}/image`}
                  alt={m.name}
                  style={{ width: 80, height: "auto" }}
                  onLoad={(e) => handleImgLoad(m.mapId, e)}
                />
              </TableCell>
              <TableCell>{m.mapId}</TableCell>
              <TableCell>{m.name}</TableCell>
              <TableCell>{m.resolution}</TableCell>
              <TableCell>
                {imgMeta[m.mapId]?.w
                  ? `${imgMeta[m.mapId].w} × ${imgMeta[m.mapId].h}`
                  : "—"}
              </TableCell>
              <TableCell>
                {Array.isArray(m.origin)
                  ? `${m.origin[0]}, ${m.origin[1]}, ${m.origin[2] ?? 0}`
                  : "—"}
              </TableCell>
              <TableCell>{m.uploadTime}</TableCell>
              <TableCell align="right">
                <Button
                  color="error"
                  size="small"
                  onClick={() => onDelete(m.mapId)}
                >
                  Delete
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <TablePagination
        component="div"
        count={data?.maps?.length || 0}
        page={page}
        onPageChange={(_, p) => setPage(p)}
        rowsPerPage={rows}
        onRowsPerPageChange={(e) => {
          setRows(parseInt(e.target.value, 10));
          setPage(0);
        }}
        rowsPerPageOptions={[5, 10, 25, 50]}
      />
    </Box>
  );
}
