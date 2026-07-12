import { useEffect, useState, type FormEvent } from "react";
import { suggestTitles, type SuggestedTitle } from "../api/client";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

type State =
  | { kind: "loading" }
  | { kind: "loaded"; titles: SuggestedTitle[] }
  | { kind: "error" };

/**
 * Show sync AI Suggested Job Titles for a freshly uploaded CV.
 *
 * The user can use a suggestion as-is or type/edit their own role; either way
 * the chosen role text is handed to the wizard via
 * {@link TitleSuggestionsProps.onUseTitle}. Suggestions are non-binding, so a
 * failed fetch is non-fatal — the custom-role entry is always available.
 */
export interface TitleSuggestionsProps {
  cvId: string;
  onUseTitle: (title: string) => void;
}

export function TitleSuggestions({ cvId, onUseTitle }: TitleSuggestionsProps) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [customRole, setCustomRole] = useState("");

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await suggestTitles(cvId);
        if (active) {
          setState({ kind: "loaded", titles: response.titles });
        }
      } catch {
        if (active) {
          setState({ kind: "error" });
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [cvId]);

  function handleCustomSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = customRole.trim();
    if (trimmed !== "") {
      onUseTitle(trimmed);
    }
  }

  return (
    <section className="mt-6 space-y-4">
      <h3 className="text-lg font-semibold">Suggested job titles</h3>

      {state.kind === "loading" && <p role="status">Reading your CV…</p>}

      {state.kind === "error" && (
        <Alert variant="destructive">
          <AlertDescription>
            We couldn&apos;t suggest titles right now — type your own role below.
          </AlertDescription>
        </Alert>
      )}

      {state.kind === "loaded" && (
        <ul className="flex list-none flex-col gap-2 p-0">
          {state.titles.map((suggestion) => (
            <li
              key={suggestion.title}
              className="flex flex-col gap-1 rounded-md border p-3"
            >
              <span className="font-medium">{suggestion.title}</span>
              <span className="text-sm text-muted-foreground">
                {suggestion.rationale}
              </span>
              <Button type="button" size="sm" onClick={() => onUseTitle(suggestion.title)}>
                Use {suggestion.title}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <form className="flex flex-col gap-3" onSubmit={handleCustomSubmit}>
        <label htmlFor="custom-role" className="text-sm font-medium">
          Or enter your own role
        </label>
        <Input
          id="custom-role"
          name="custom-role"
          type="text"
          className="text-foreground"
          value={customRole}
          onChange={(event) => setCustomRole(event.target.value)}
          placeholder="e.g. Frontend Developer"
        />
        <Button type="submit" disabled={customRole.trim() === ""}>
          Use this role
        </Button>
      </form>
    </section>
  );
}
