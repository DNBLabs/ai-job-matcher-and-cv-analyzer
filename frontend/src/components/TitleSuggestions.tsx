import { useEffect, useState, type FormEvent } from "react";
import { suggestTitles, type SuggestedTitle } from "../api/client";

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
    <section className="title-suggestions">
      <h3>Suggested job titles</h3>

      {state.kind === "loading" && <p role="status">Reading your CV…</p>}

      {state.kind === "error" && (
        <p role="alert" className="form-error">
          We couldn't suggest titles right now — type your own role below.
        </p>
      )}

      {state.kind === "loaded" && (
        <ul className="suggestion-list">
          {state.titles.map((suggestion) => (
            <li key={suggestion.title}>
              <span className="suggestion-title">{suggestion.title}</span>
              <span className="suggestion-rationale">{suggestion.rationale}</span>
              <button type="button" onClick={() => onUseTitle(suggestion.title)}>
                Use {suggestion.title}
              </button>
            </li>
          ))}
        </ul>
      )}

      <form className="custom-role" onSubmit={handleCustomSubmit}>
        <label htmlFor="custom-role">Or enter your own role</label>
        <input
          id="custom-role"
          name="custom-role"
          type="text"
          value={customRole}
          onChange={(event) => setCustomRole(event.target.value)}
          placeholder="e.g. Frontend Developer"
        />
        <button type="submit" disabled={customRole.trim() === ""}>
          Use this role
        </button>
      </form>
    </section>
  );
}
