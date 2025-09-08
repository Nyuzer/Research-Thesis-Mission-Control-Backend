import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { SnackbarProvider } from "notistack";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { startWS } from "./utils/ws";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <SnackbarProvider maxSnack={3} autoHideDuration={4000}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SnackbarProvider>
    </QueryClientProvider>
  </React.StrictMode>
);

startWS();
