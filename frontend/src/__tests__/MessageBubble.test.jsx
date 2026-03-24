import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { MessageBubble } from "../components/MessageBubble";

describe("MessageBubble", () => {
  const userMessage = { role: "user", content: "What is annual leave?" };
  const assistantMessage = {
    role: "assistant",
    content: "Annual leave is governed by the Employment Act.",
    isStreaming: false,
    sources: [
      { label: "Employment Act, s 43", url: "https://example.com" },
    ],
  };

  it("renders user message with 'You' label", () => {
    render(<MessageBubble message={userMessage} messageIndex={0} />);
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText(/annual leave/i)).toBeInTheDocument();
  });

  it("renders assistant message with 'HR Assistant' label", () => {
    render(<MessageBubble message={assistantMessage} messageIndex={1} />);
    expect(screen.getByText("HR Assistant")).toBeInTheDocument();
  });

  it("shows sources toggle for assistant messages with sources", () => {
    render(<MessageBubble message={assistantMessage} messageIndex={1} />);
    expect(screen.getByText(/sources \(1\)/i)).toBeInTheDocument();
  });

  it("expands sources on toggle click", async () => {
    const user = userEvent.setup();
    render(<MessageBubble message={assistantMessage} messageIndex={1} />);

    await user.click(screen.getByText(/sources \(1\)/i));
    expect(screen.getByText("Employment Act, s 43")).toBeInTheDocument();
  });

  it("shows feedback buttons for completed assistant messages", () => {
    render(
      <MessageBubble
        message={assistantMessage}
        messageIndex={1}
        onFeedback={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Mark as helpful")).toBeInTheDocument();
    expect(screen.getByLabelText("Mark as not helpful")).toBeInTheDocument();
  });

  it("does not show feedback buttons for user messages", () => {
    render(<MessageBubble message={userMessage} messageIndex={0} />);
    expect(screen.queryByLabelText("Mark as helpful")).not.toBeInTheDocument();
  });

  it("does not show feedback buttons while streaming", () => {
    const streaming = { ...assistantMessage, isStreaming: true };
    render(<MessageBubble message={streaming} messageIndex={1} />);
    expect(screen.queryByLabelText("Mark as helpful")).not.toBeInTheDocument();
  });

  it("calls onFeedback when thumbs up is clicked", async () => {
    const onFeedback = vi.fn();
    const user = userEvent.setup();
    render(
      <MessageBubble
        message={assistantMessage}
        messageIndex={1}
        onFeedback={onFeedback}
      />
    );

    await user.click(screen.getByLabelText("Mark as helpful"));
    expect(onFeedback).toHaveBeenCalledWith(1, "up");
  });

  it("shows thanks message after feedback", async () => {
    const user = userEvent.setup();
    render(
      <MessageBubble
        message={assistantMessage}
        messageIndex={1}
        onFeedback={vi.fn()}
      />
    );

    await user.click(screen.getByLabelText("Mark as helpful"));
    expect(screen.getByText(/thanks for the feedback/i)).toBeInTheDocument();
  });

  it("shows thinking steps when present", () => {
    const withThinking = {
      ...assistantMessage,
      thinkingSteps: ["Searching Employment Act...", "Calculating entitlement..."],
    };
    render(<MessageBubble message={withThinking} messageIndex={1} />);
    expect(screen.getByText("Searching Employment Act...")).toBeInTheDocument();
    expect(screen.getByText("Calculating entitlement...")).toBeInTheDocument();
  });
});
