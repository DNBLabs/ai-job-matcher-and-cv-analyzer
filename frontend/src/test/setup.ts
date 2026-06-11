import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// vite.config sets globals:false, so Testing Library's auto-cleanup hook is not
// registered. Tear down the rendered DOM between tests explicitly.
afterEach(cleanup);
