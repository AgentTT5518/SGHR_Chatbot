import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

// Mock the admin API module to avoid network calls
vi.mock("../api/adminApi", () => ({
  fetchHealth: vi.fn().mockResolvedValue({ status: "ok" }),
  fetchCollections: vi.fn().mockResolvedValue({ employment_act: 166, mom_guidelines: 20 }),
  fetchSourceHealth: vi.fn().mockResolvedValue({ total: 5, ok: 5, results: [] }),
  triggerIngest: vi.fn().mockResolvedValue({ status: "started" }),
  fetchFeedback: vi.fn().mockResolvedValue({ records: [] }),
  fetchFeedbackStats: vi.fn().mockResolvedValue({ up: 0, down: 0 }),
  fetchMetrics: vi.fn().mockResolvedValue({}),
  fetchVerifiedAnswers: vi.fn().mockResolvedValue({ answers: [] }),
  addVerifiedAnswer: vi.fn().mockResolvedValue({ success: true }),
  deleteVerifiedAnswer: vi.fn().mockResolvedValue({ success: true }),
  fetchCacheCandidates: vi.fn().mockResolvedValue({ candidates: [] }),
  fetchFaqPatterns: vi.fn().mockResolvedValue({ top_patterns: [], knowledge_gaps: [] }),
  getAdminKey: vi.fn().mockReturnValue("test-key"),
  setAdminKey: vi.fn(),
}));

import { AdminDashboard } from "../pages/AdminDashboard";

describe("AdminDashboard", () => {
  it("renders the dashboard title", () => {
    render(<AdminDashboard onClose={vi.fn()} />);
    expect(screen.getByText("Admin Dashboard")).toBeInTheDocument();
  });

  it("renders all navigation tabs", () => {
    render(<AdminDashboard onClose={vi.fn()} />);
    const tabs = ["Health", "Ingestion", "Feedback", "Verified Answers", "FAQ Patterns", "Metrics"];
    for (const tab of tabs) {
      expect(screen.getByRole("button", { name: tab })).toBeInTheDocument();
    }
  });

  it("renders back to chat button", () => {
    render(<AdminDashboard onClose={vi.fn()} />);
    expect(screen.getByText(/back to chat/i)).toBeInTheDocument();
  });

  it("calls onClose when back button is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<AdminDashboard onClose={onClose} />);

    await user.click(screen.getByText(/back to chat/i));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("switches tabs on click", async () => {
    const user = userEvent.setup();
    render(<AdminDashboard onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Feedback" }));
    // The Feedback tab should now be active (has active class or similar)
    const feedbackTab = screen.getByRole("button", { name: "Feedback" });
    expect(feedbackTab.className).toContain("active");
  });

  it("renders admin key input", () => {
    render(<AdminDashboard onClose={vi.fn()} />);
    expect(screen.getByLabelText(/admin api key/i)).toBeInTheDocument();
  });
});
