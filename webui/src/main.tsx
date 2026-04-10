import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import App from "./App";
import { startWS } from "./utils/ws";
import { useAuthStore } from "./utils/auth";
import "./index.css";

const queryClient = new QueryClient();

// Apply stored theme before first render to avoid flash
const stored = localStorage.getItem("theme");
if (stored === "light") {
  document.documentElement.classList.remove("dark");
} else {
  document.documentElement.classList.add("dark");
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
        <Toaster
          position="bottom-left"
          duration={10000}
          closeButton
          toastOptions={{
            style: {
              background: "var(--card)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            },
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  </React.StrictMode>
);

// Start WS only if already authenticated
if (useAuthStore.getState().isAuthenticated) {
  startWS();
}

// Re-start/stop WS when auth state changes
useAuthStore.subscribe((state, prev) => {
  if (state.isAuthenticated && !prev.isAuthenticated) {
    startWS();
  }
});
