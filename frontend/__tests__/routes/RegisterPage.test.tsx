import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, it, expect } from "vitest";
import RegisterPage from "@/routes/RegisterPage";
import { renderWithProviders } from "@/testUtils";
import { server } from "@/msw/server";

async function fillBaseForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/First Name/i), "Alice");
  await user.type(screen.getByLabelText(/Last Name/i), "Liddell");
  await user.type(screen.getByLabelText(/Email/i), "alice@example.com");
  await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
  await user.type(screen.getByLabelText(/Confirm Password/i), "securepassword");
}

describe("RegisterPage", () => {
  it("happy path — fills form, submits, shows OTP step", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await fillBaseForm(user);
    await user.click(screen.getByRole("button", { name: /Register/i }));

    await waitFor(() => {
      expect(screen.getByText(/Verify Your Account/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/Enter the code/i)).toBeInTheDocument();
  });

  it("loading state — button shows loading text while submitting", async () => {
    server.use(
      http.post("/api/v1/auth/register", async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json(
          { id: 1, message: "Registration successful." },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await fillBaseForm(user);
    await user.click(screen.getByRole("button", { name: /Register/i }));

    expect(screen.getByRole("button", { name: /Creating account/i })).toBeInTheDocument();
  });

  it("error state — shows registration error from API", async () => {
    server.use(
      http.post("/api/v1/auth/register", () =>
        HttpResponse.json(
          { error: { code: "REGISTRATION_FAILED", message: "Please check your details and try again" } },
          { status: 422 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await fillBaseForm(user);
    await user.click(screen.getByRole("button", { name: /Register/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/Please check your details/i);
  });

  it("client validation — password too short shows error", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await user.type(screen.getByLabelText(/First Name/i), "Alice");
    await user.type(screen.getByLabelText(/Last Name/i), "Liddell");
    await user.type(screen.getByLabelText(/Email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "short");
    await user.type(screen.getByLabelText(/Confirm Password/i), "short");
    await user.click(screen.getByRole("button", { name: /Register/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/at least 8 characters/i);
  });

  it("password mismatch shows error", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await user.type(screen.getByLabelText(/First Name/i), "Alice");
    await user.type(screen.getByLabelText(/Last Name/i), "Liddell");
    await user.type(screen.getByLabelText(/Email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
    await user.type(screen.getByLabelText(/Confirm Password/i), "differentpassword");
    await user.click(screen.getByRole("button", { name: /Register/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/do not match/i);
  });

  it("missing email and phone shows error", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await user.type(screen.getByLabelText(/First Name/i), "Alice");
    await user.type(screen.getByLabelText(/Last Name/i), "Liddell");
    // Leave email and phone empty
    await user.type(screen.getByLabelText(/^Password$/i), "securepassword");
    await user.type(screen.getByLabelText(/Confirm Password/i), "securepassword");
    await user.click(screen.getByRole("button", { name: /Register/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/email or phone/i);
  });

  it("OTP submission — enter OTP, verify endpoint called", async () => {
    let verifyEndpointCalled = false;
    server.use(
      http.post("/api/v1/auth/verify/email", () => {
        verifyEndpointCalled = true;
        return HttpResponse.json({ message: "Email verified" });
      }),
    );

    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />);

    await fillBaseForm(user);
    await user.click(screen.getByRole("button", { name: /Register/i }));

    await waitFor(() => {
      expect(screen.getByText(/Verify Your Account/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/Enter the code/i), "123456");
    await user.click(screen.getByRole("button", { name: /Verify Email/i }));

    await waitFor(() => {
      expect(verifyEndpointCalled).toBe(true);
    });
  });
});
