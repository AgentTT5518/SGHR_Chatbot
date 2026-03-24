import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { InputBar } from "../components/InputBar";

describe("InputBar", () => {
  it("renders textarea and send button", () => {
    render(<InputBar onSend={vi.fn()} disabled={false} />);
    expect(screen.getByPlaceholderText(/ask about/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send/i })).toBeInTheDocument();
  });

  it("send button is disabled when textarea is empty", () => {
    render(<InputBar onSend={vi.fn()} disabled={false} />);
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("calls onSend with trimmed text on submit", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} disabled={false} />);

    const textarea = screen.getByPlaceholderText(/ask about/i);
    await user.type(textarea, "  What is annual leave?  ");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(onSend).toHaveBeenCalledWith("What is annual leave?");
  });

  it("clears textarea after submit", async () => {
    const user = userEvent.setup();
    render(<InputBar onSend={vi.fn()} disabled={false} />);

    const textarea = screen.getByPlaceholderText(/ask about/i);
    await user.type(textarea, "test message");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(textarea).toHaveValue("");
  });

  it("disables textarea and button when disabled prop is true", () => {
    render(<InputBar onSend={vi.fn()} disabled={true} />);
    expect(screen.getByPlaceholderText(/ask about/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("does not call onSend when disabled", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<InputBar onSend={onSend} disabled={true} />);

    const textarea = screen.getByPlaceholderText(/ask about/i);
    await user.type(textarea, "test");

    expect(onSend).not.toHaveBeenCalled();
  });
});
