import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { Button } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

/**
 * Persistent top navigation for authenticated routes: brand, primary links,
 * optional admin entry, and a user menu with sign-out.
 */
export function Navbar() {
  const { user, signOut } = useAuth();

  return (
    <nav className="flex min-w-0 items-center justify-between gap-2 border-b bg-background px-4 py-3 sm:gap-4">
      <Link
        to="/dashboard"
        className="shrink-0 text-sm font-semibold text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        Get Me a Job
      </Link>

      <div className="hidden min-w-0 flex-1 items-center justify-center gap-4 sm:flex">
        <Link
          to="/dashboard"
          className="text-sm font-medium text-foreground hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          Dashboard
        </Link>
        <Link
          to="/runs/new"
          className="text-sm font-medium text-foreground hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          New Run
        </Link>
      </div>

      <div className="flex min-w-0 shrink items-center gap-2 sm:gap-4">
        {user?.is_admin && (
          <Link
            to="/admin"
            className="shrink-0 text-sm font-medium text-foreground hover:text-foreground/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            Admin
          </Link>
        )}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              className="max-w-[10rem] truncate sm:max-w-xs"
            >
              {user?.email}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="truncate">
              {user?.email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="sm:hidden" />
            <DropdownMenuItem asChild className="sm:hidden">
              <Link to="/dashboard">Dashboard</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild className="sm:hidden">
              <Link to="/runs/new">New Run</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => void signOut()}>
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </nav>
  );
}
