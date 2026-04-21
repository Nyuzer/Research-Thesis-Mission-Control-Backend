import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchUsers, createUser, updateUser, deleteUser,
  fetchRobotKeys, createRobotKey, deleteRobotKey, RobotKeyCreated,
} from "@/utils/api";
import { useAuthStore } from "@/utils/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ConfirmDeleteDialog from "@/components/ConfirmDeleteDialog";
import { showToast } from "@/lib/toast";
import { Plus, Trash2, Pencil, X, Check, Shield, Eye, Wrench, Search, Key, Copy, Bot } from "lucide-react";

const ROLE_ICONS: Record<string, typeof Shield> = {
  admin: Shield,
  operator: Wrench,
  viewer: Eye,
};

const ROLE_COLORS: Record<string, string> = {
  admin: "text-red-400 bg-red-500/10",
  operator: "text-cyan bg-cyan/10",
  viewer: "text-muted-foreground bg-muted",
};

export default function UsersPage() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((s) => s.user);
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  // Filters
  const [q, setQ] = useState("");
  const [fRole, setFRole] = useState("all");
  const [fStatus, setFStatus] = useState("all");

  const hasFilters = Boolean(q || fRole !== "all" || fStatus !== "all");
  const clearFilters = () => { setQ(""); setFRole("all"); setFStatus("all"); };

  const filteredUsers = useMemo(() => {
    return (users as any[]).filter((u) => {
      if (q) {
        const text = `${u.username} ${u.email}`.toLowerCase();
        if (!text.includes(q.toLowerCase())) return false;
      }
      if (fRole !== "all" && u.role !== fRole) return false;
      if (fStatus !== "all") {
        const active = fStatus === "active";
        if (u.is_active !== active) return false;
      }
      return true;
    });
  }, [users, q, fRole, fStatus]);

  // Create form
  const [form, setForm] = useState({ email: "", username: "", password: "", role: "operator" });

  const createMut = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setShowCreate(false);
      setForm({ email: "", username: "", password: "", role: "operator" });
      showToast("User created", "success");
    },
    onError: (e: any) => showToast(e.message, "error"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => updateUser(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditId(null);
      showToast("User updated", "success");
    },
    onError: (e: any) => showToast(e.message, "error"),
  });

  const deleteMut = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      showToast("User deleted", "success");
    },
    onError: (e: any) => showToast(e.message, "error"),
  });

  // Edit form state
  const [editForm, setEditForm] = useState<any>({});

  const startEdit = (user: any) => {
    setEditId(user.id);
    setEditForm({ email: user.email, username: user.username, role: user.role, password: "" });
  };

  const saveEdit = () => {
    const data: any = {};
    if (editForm.email) data.email = editForm.email;
    if (editForm.username) data.username = editForm.username;
    if (editForm.role) data.role = editForm.role;
    if (editForm.password) data.password = editForm.password;
    updateMut.mutate({ id: editId!, data });
  };

  const handleDeleteClick = (u: any) => {
    if (currentUser && u.id === currentUser.id) {
      showToast("You cannot delete your own account", "warning");
      return;
    }
    setDeleteTarget({ id: u.id, name: u.username });
  };

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-4 overflow-auto h-full">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">User Management</h2>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-1" /> Add User
        </Button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 sm:flex sm:flex-wrap sm:items-center gap-2">
        <div className="relative col-span-2">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search name or email..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="pl-7 h-8 w-full sm:w-[200px] text-xs"
          />
        </div>
        <Select value={fRole} onValueChange={setFRole}>
          <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs">
            <SelectValue placeholder="Role" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All roles</SelectItem>
            <SelectItem value="admin">Admin</SelectItem>
            <SelectItem value="operator">Operator</SelectItem>
            <SelectItem value="viewer">Viewer</SelectItem>
          </SelectContent>
        </Select>
        <Select value={fStatus} onValueChange={setFStatus}>
          <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
        <div className="col-span-2 sm:col-span-1 flex items-center justify-between sm:justify-start gap-2">
          {hasFilters && (
            <Button variant="ghost" size="sm" className="text-xs h-8 gap-1 text-muted-foreground" onClick={clearFilters}>
              <X className="h-3 w-3" /> Clear
            </Button>
          )}
          <span className="text-xs text-muted-foreground sm:ml-auto">{filteredUsers.length} users</span>
        </div>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-card border border-border rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-medium">New User</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              placeholder="Email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
            />
            <input
              placeholder="Username"
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
            />
            <input
              placeholder="Password"
              type="password"
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
            />
            <select
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
              className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
            >
              <option value="admin">Admin</option>
              <option value="operator">Operator</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => createMut.mutate(form)}
              disabled={createMut.isPending}
            >
              Create
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Users table */}
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading...</div>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-left">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((u: any) => {
                const RoleIcon = ROLE_ICONS[u.role] || Eye;
                const isEditing = editId === u.id;
                const isSelf = currentUser?.id === u.id;

                return (
                  <tr key={u.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <input
                          value={editForm.username}
                          onChange={(e) =>
                            setEditForm((f: any) => ({ ...f, username: e.target.value }))
                          }
                          className="px-2 py-1 rounded border border-border bg-background text-sm w-full text-foreground"
                        />
                      ) : (
                        <span className="text-foreground font-medium">
                          {u.username}
                          {isSelf && <span className="text-[10px] text-muted-foreground ml-1.5">(you)</span>}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <input
                          value={editForm.email}
                          onChange={(e) =>
                            setEditForm((f: any) => ({ ...f, email: e.target.value }))
                          }
                          className="px-2 py-1 rounded border border-border bg-background text-sm w-full text-foreground"
                        />
                      ) : (
                        <span className="text-muted-foreground">{u.email}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <select
                          value={editForm.role}
                          onChange={(e) =>
                            setEditForm((f: any) => ({ ...f, role: e.target.value }))
                          }
                          className="px-2 py-1 rounded border border-border bg-background text-sm text-foreground"
                        >
                          <option value="admin">Admin</option>
                          <option value="operator">Operator</option>
                          <option value="viewer">Viewer</option>
                        </select>
                      ) : (
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${ROLE_COLORS[u.role] || ""}`}
                        >
                          <RoleIcon className="h-3 w-3" />
                          {u.role}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs ${u.is_active ? "text-green-400" : "text-red-400"}`}
                      >
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {isEditing ? (
                        <div className="flex items-center justify-end gap-1">
                          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={saveEdit}>
                            <Check className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            onClick={() => setEditId(null)}
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7"
                            onClick={() => startEdit(u)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-7 w-7 text-red-400 hover:text-red-300"
                            disabled={isSelf}
                            title={isSelf ? "Cannot delete yourself" : undefined}
                            onClick={() => handleDeleteClick(u)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filteredUsers.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground text-xs">
                    {hasFilters ? "No users match filters" : "No users"}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        title="Delete User"
        description={`Are you sure you want to delete user "${deleteTarget?.name}"? This action cannot be undone.`}
        onConfirm={() => {
          if (deleteTarget) deleteMut.mutate(deleteTarget.id);
          setDeleteTarget(null);
        }}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
      />

      {/* Robot API Keys section */}
      <RobotKeysSection />
    </div>
  );
}

/* ─── Robot API Keys ─── */

function RobotKeysSection() {
  const queryClient = useQueryClient();
  const { data: keys = [], isLoading } = useQuery({
    queryKey: ["robot-keys"],
    queryFn: fetchRobotKeys,
  });

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: "", robot_id: "" });
  const [createdKey, setCreatedKey] = useState<RobotKeyCreated | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  const createMut = useMutation({
    mutationFn: createRobotKey,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["robot-keys"] });
      setCreatedKey(data);
      setShowCreate(false);
      setForm({ name: "", robot_id: "" });
    },
    onError: (e: any) => showToast(e.message, "error"),
  });

  const deleteMut = useMutation({
    mutationFn: deleteRobotKey,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["robot-keys"] });
      showToast("Robot key deleted", "success");
    },
    onError: (e: any) => showToast(e.message, "error"),
  });

  const copyKey = async (key: string) => {
    await navigator.clipboard.writeText(key);
    showToast("API key copied to clipboard", "success");
  };

  return (
    <>
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-lg font-semibold text-foreground">Robot API Keys</h2>
        </div>
        <Button size="sm" onClick={() => setShowCreate(true)}>
          <Plus className="h-4 w-4 mr-1" /> New Key
        </Button>
      </div>

      <p className="text-xs text-muted-foreground">
        Create API keys for robot bridges. Set the key as <code className="px-1 py-0.5 rounded bg-muted text-foreground">ROBOT_API_KEY</code> in the robot's environment.
      </p>

      {/* Created key banner — shown once */}
      {createdKey && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 space-y-2">
          <p className="text-sm font-medium text-green-400">
            Key created — copy it now, it won't be shown again!
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 px-3 py-2 rounded bg-background border border-border text-sm text-foreground font-mono break-all select-all">
              {createdKey.api_key}
            </code>
            <Button size="icon" variant="ghost" className="h-8 w-8 shrink-0" onClick={() => copyKey(createdKey.api_key)}>
              <Copy className="h-4 w-4" />
            </Button>
          </div>
          <Button size="sm" variant="ghost" className="text-xs" onClick={() => setCreatedKey(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="bg-card border border-border rounded-lg p-4 space-y-3">
          <h3 className="text-sm font-medium">New Robot Key</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              placeholder="Name (e.g. Lab Robot 01)"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
            />
            <input
              placeholder="Robot ID (e.g. Professor_Robot_01)"
              value={form.robot_id}
              onChange={(e) => setForm((f) => ({ ...f, robot_id: e.target.value }))}
              className="px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground"
            />
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => createMut.mutate(form)}
              disabled={createMut.isPending || !form.name || !form.robot_id}
            >
              Generate Key
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Keys table */}
      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading...</div>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-left">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Robot ID</th>
                <th className="px-4 py-3 font-medium">Key</th>
                <th className="px-4 py-3 font-medium">Created</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(keys as any[]).map((k: any) => (
                <tr key={k.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1.5 text-foreground font-medium">
                      <Key className="h-3.5 w-3.5 text-amber-400" />
                      {k.name}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{k.robot_id}</td>
                  <td className="px-4 py-3 text-muted-foreground font-mono text-xs">{k.key_prefix}</td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {new Date(k.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-red-400 hover:text-red-300"
                      onClick={() => setDeleteTarget({ id: k.id, name: k.name })}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
              {keys.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground text-xs">
                    No robot keys yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        title="Delete Robot Key"
        description={`Are you sure you want to delete key "${deleteTarget?.name}"? The robot using this key will lose access immediately.`}
        onConfirm={() => {
          if (deleteTarget) deleteMut.mutate(deleteTarget.id);
          setDeleteTarget(null);
        }}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
      />
    </>
  );
}
