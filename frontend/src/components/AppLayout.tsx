import type { ReactNode } from "react";
import { Navbar } from "./Navbar";

/**
 * Authenticated app shell: persistent top navbar plus a main content slot.
 */
export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Navbar />
      <main>{children}</main>
    </>
  );
}
