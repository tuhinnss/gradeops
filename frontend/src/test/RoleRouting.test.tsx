import { act, render, screen, waitFor } from "@testing-library/react";
import { createContext, useContext, useState } from "react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
const push = vi.fn();
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => "/professor/exams",
  useSearchParams: () => search,
}));

type Session = { status: string; user: { role: string; full_name: string; email: string } | null; authEnabled: boolean | null; login: ReturnType<typeof vi.fn>; logout: () => void; refresh: () => Promise<void> };
let session: Session;
// Stateful fake of the session context: a successful login re-renders consumers,
// exactly like the real provider.
const SessionCtx = createContext<Session | null>(null);
vi.mock("@/lib/session", () => ({ useSession: () => useContext(SessionCtx) ?? session }));

function FakeSessionProvider({ initial, children }: { initial: Session; children: React.ReactNode }) {
  const [state, setState] = useState(initial);
  const login = vi.fn(async (email: string, password: string) => {
    const user = await initial.login(email, password);
    setState((s) => ({ ...s, status: "authenticated", user }));
    return user;
  });
  session = { ...state, login };
  return <SessionCtx.Provider value={session}>{children}</SessionCtx.Provider>;
}

import LoginPage from "@/app/login/page";
import { RoleGuard } from "@/components/layout/RoleGuard";

function makeSession(partial: Partial<Session>): Session {
  return { status: "anonymous", user: null, authEnabled: true, login: vi.fn(), logout: vi.fn(), refresh: vi.fn(), ...partial };
}

beforeEach(() => {
  search = new URLSearchParams();
});

describe("RoleGuard", () => {
  it("sends anonymous users to login, remembering where they were", async () => {
    session = makeSession({ status: "anonymous" });
    render(<RoleGuard role="professor">secret</RoleGuard>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login?next=%2Fprofessor%2Fexams"));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("shows 403 to a TA on professor pages and redirects to /ta", async () => {
    vi.useFakeTimers();
    session = makeSession({ status: "authenticated", user: { role: "ta", full_name: "Rahul", email: "r@x" } });
    render(<RoleGuard role="professor">secret</RoleGuard>);
    expect(screen.getByRole("alert")).toHaveTextContent("403");
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(replace).toHaveBeenCalledWith("/ta");
    vi.useRealTimers();
  });

  it("renders the page for the right role", () => {
    session = makeSession({ status: "authenticated", user: { role: "professor", full_name: "Dr S", email: "s@x" } });
    render(<RoleGuard role="professor">secret</RoleGuard>);
    expect(screen.getByText("secret")).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });

  it("shows nothing sensitive while the session is loading", () => {
    session = makeSession({ status: "loading" });
    render(<RoleGuard role="ta">secret</RoleGuard>);
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });
});

describe("Login routing", () => {
  async function signIn(role: "professor" | "ta") {
    const backend = vi.fn().mockResolvedValue({ role, email: "u@x", full_name: "U" });
    render(
      <FakeSessionProvider initial={makeSession({ login: backend })}>
        <LoginPage />
      </FakeSessionProvider>,
    );
    await userEvent.type(screen.getByLabelText("Email"), "u@uni.edu");
    await userEvent.type(screen.getByLabelText("Password"), "secret-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(backend).toHaveBeenCalledWith("u@uni.edu", "secret-pass");
  }

  it("routes a professor to /professor", async () => {
    await signIn("professor");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/professor"));
  });

  it("routes a TA to /ta", async () => {
    await signIn("ta");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/ta"));
  });

  it("returns to the requested page when the role may open it", async () => {
    search = new URLSearchParams("next=/ta/reviews/abc");
    await signIn("ta");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/ta/reviews/abc"));
  });

  it("ignores a next param pointing at another role's area", async () => {
    search = new URLSearchParams("next=/professor/exams");
    await signIn("ta");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/ta"));
  });

  it("shows the server's error on bad credentials", async () => {
    render(
      <FakeSessionProvider initial={makeSession({ login: vi.fn().mockRejectedValue(new Error("Invalid email or password")) })}>
        <LoginPage />
      </FakeSessionProvider>,
    );
    await userEvent.type(screen.getByLabelText("Email"), "u@uni.edu");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(replace).not.toHaveBeenCalled();
  });
});
