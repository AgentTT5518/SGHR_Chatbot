import { useState, useEffect } from "react";
import { checkHealth } from "../api/chatApi";

export function StatusBanner() {
  const [status, setStatus] = useState("checking"); // "checking" | "ok" | "degraded" | "offline"

  useEffect(() => {
    checkHealth().then((health) => {
      if (!health) {
        setStatus("offline");
      } else if (health.status === "ok") {
        setStatus("ok");
      } else {
        setStatus("degraded");
      }
    });
  }, []);

  if (status === "ok") return null; // no banner when healthy

  const messages = {
    checking: { text: "Connecting to backend…", className: "banner-checking" },
    degraded: {
      text: "Backend is starting up (loading AI model, ~30s)…",
      className: "banner-warning",
    },
    offline: {
      text: "Cannot reach the backend. Make sure the server is running on port 8000.",
      className: "banner-error",
    },
  };

  const { text, className } = messages[status];
  return <div className={`status-banner ${className}`}>{text}</div>;
}
