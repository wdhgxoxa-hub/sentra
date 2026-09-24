import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";

import App from "@/App";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { queryClient } from "@/lib/queries";
import { useSettingsStore } from "@/stores/settingsStore";
import "@/styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      {/* Última red: ningún fallo de render deja la ventana vacía. Los textos
          se leen una vez del store, sin suscribirse, por si lo que falla es él. */}
      <ErrorBoundary textos={useSettingsStore.getState().t.error}>
        <App />
      </ErrorBoundary>
    </QueryClientProvider>
  </React.StrictMode>,
);
